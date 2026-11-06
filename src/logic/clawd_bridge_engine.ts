export interface BridgeState {
  has_media: boolean;
  is_playing: boolean;
  player: string;
  artist: string;
  title: string;
  position_ms: number;
  duration_ms: number;
  position_known: boolean;
  timestamp: number;
}

export interface JitterFilterState {
  trackBasePos: number; // in seconds
  trackBaseTime: number; // in seconds (time.monotonic)
  userOffset: number; // in seconds
  isPlaying: boolean;
}

/**
 * Clawd Bridge Stepped Backoff Manager
 * - Default polling: 350-400 ms (nominal 380 ms)
 * - 5 consecutive errors: switch to 3000 ms (3.0s)
 * - 1 successful HTTP 200: immediately return to 380 ms
 */
export class BridgeBackoffManager {
  private consecutiveErrors = 0;
  private currentIntervalMs = 380;

  public recordSuccess(): number {
    this.consecutiveErrors = 0;
    this.currentIntervalMs = 380;
    return this.currentIntervalMs;
  }

  public recordError(): number {
    this.consecutiveErrors += 1;
    if (this.consecutiveErrors >= 5) {
      this.currentIntervalMs = 3000;
    }
    return this.currentIntervalMs;
  }

  public getIntervalMs(): number {
    return this.currentIntervalMs;
  }

  public getConsecutiveErrors(): number {
    return this.consecutiveErrors;
  }

  public isInBackoff(): boolean {
    return this.consecutiveErrors >= 5;
  }
}

/**
 * Jitter filter and timeline calculation as specified in ТЗ Section 2.2:
 * T_calc = _track_base_pos + (now - _track_base_time)
 * T_karaoke = T_calc + _user_offset
 * Jitter threshold: |T_new - T_calc| > 0.25s
 */
export function calculateTrackPositions(
  state: JitterFilterState,
  now: number
): { tCalcRaw: number; tKaraoke: number } {
  const tCalcRaw = state.isPlaying
    ? state.trackBasePos + Math.max(0, now - state.trackBaseTime)
    : state.trackBasePos;
  const tKaraoke = tCalcRaw + state.userOffset;
  return { tCalcRaw, tKaraoke };
}

export function updateBridgePosition(
  state: JitterFilterState,
  newPositionMs: number,
  now: number,
  isPlaying: boolean
): { updatedBase: boolean; driftSec: number } {
  const tNew = newPositionMs / 1000.0;
  const { tCalcRaw } = calculateTrackPositions(state, now);
  const driftSec = Math.abs(tNew - tCalcRaw);

  state.isPlaying = isPlaying;

  // Threshold is strictly 0.25 seconds
  if (driftSec > 0.25) {
    state.trackBasePos = tNew;
    state.trackBaseTime = now;
    return { updatedBase: true, driftSec };
  }

  return { updatedBase: false, driftSec };
}

/**
 * Tap-to-Sync calibration:
 * _user_offset = T_line - T_calc_raw
 */
export function calibrateTapToSync(
  state: JitterFilterState,
  lineTimestampSec: number,
  now: number
): number {
  const { tCalcRaw } = calculateTrackPositions(state, now);
  const newOffset = lineTimestampSec - tCalcRaw;
  state.userOffset = newOffset;
  return newOffset;
}

/**
 * Host header check for Clawd Bridge (Specification v1.3):
 * host.split(":")[0] allowed strictly 127.0.0.1 and localhost
 */
export function validateBridgeHostHeader(hostHeader: string | undefined): boolean {
  if (!hostHeader) return false;
  const hostname = hostHeader.split(':')[0].trim().toLowerCase();
  return hostname === '127.0.0.1' || hostname === 'localhost';
}
