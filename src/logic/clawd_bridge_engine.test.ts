import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BridgeBackoffManager,
  calculateTrackPositions,
  updateBridgePosition,
  calibrateTapToSync,
  validateBridgeHostHeader,
  JitterFilterState,
} from './clawd_bridge_engine';

test('BridgeBackoffManager transitions to 3.0s after exactly 5 errors', () => {
  const manager = new BridgeBackoffManager();
  assert.equal(manager.getIntervalMs(), 380);

  // 1-4 errors: still normal interval
  for (let i = 1; i <= 4; i++) {
    manager.recordError();
    assert.equal(manager.isInBackoff(), false, `Error count ${i} should not trigger backoff`);
    assert.equal(manager.getIntervalMs(), 380);
  }

  // 5th error: activates 3.0s backoff
  manager.recordError();
  assert.equal(manager.isInBackoff(), true, '5 errors must trigger backoff');
  assert.equal(manager.getIntervalMs(), 3000);

  // Subsequent errors stay in backoff
  manager.recordError();
  assert.equal(manager.getIntervalMs(), 3000);

  // Successful response immediately resets to 380 ms
  manager.recordSuccess();
  assert.equal(manager.isInBackoff(), false);
  assert.equal(manager.getIntervalMs(), 380);
  assert.equal(manager.getConsecutiveErrors(), 0);
});

test('Jitter filter ignores drift <= 0.25s and updates when > 0.25s', () => {
  const state: JitterFilterState = {
    trackBasePos: 10.0,
    trackBaseTime: 100.0,
    userOffset: 0.0,
    isPlaying: true,
  };

  // At time 102.0, calculated pos is 10.0 + (102.0 - 100.0) = 12.0s
  // If bridge reports 12150 ms (12.15s), drift is 0.15s (<= 0.25s) -> do NOT touch base
  const res1 = updateBridgePosition(state, 12150, 102.0, true);
  assert.equal(res1.updatedBase, false);
  assert.equal(state.trackBasePos, 10.0);
  assert.equal(state.trackBaseTime, 100.0);

  // If bridge reports 12300 ms (12.30s), drift is 0.30s (> 0.25s) -> MUST update base
  const res2 = updateBridgePosition(state, 12300, 102.0, true);
  assert.equal(res2.updatedBase, true);
  assert.equal(state.trackBasePos, 12.3);
  assert.equal(state.trackBaseTime, 102.0);
});

test('Tap-to-sync computes correct user offset without resetting upon jitter jumps', () => {
  const state: JitterFilterState = {
    trackBasePos: 30.0,
    trackBaseTime: 200.0,
    userOffset: 0.0,
    isPlaying: true,
  };

  // Now is 205.0 -> tCalcRaw = 35.0s
  // User taps line with timestamp 37.5s
  const offset = calibrateTapToSync(state, 37.5, 205.0);
  assert.equal(offset, 2.5);
  assert.equal(state.userOffset, 2.5);

  const { tKaraoke } = calculateTrackPositions(state, 205.0);
  assert.equal(tKaraoke, 37.5);

  // Next bridge sync jumps by >0.25s (seek or timing adjustment)
  // State base updates, but userOffset remains 2.5s
  updateBridgePosition(state, 36000, 205.0, true);
  assert.equal(state.userOffset, 2.5, 'User offset must be preserved across base updates');
  assert.equal(state.trackBasePos, 36.0);
});

test('Bridge host header validation allows only 127.0.0.1 and localhost', () => {
  assert.equal(validateBridgeHostHeader('127.0.0.1:44444'), true);
  assert.equal(validateBridgeHostHeader('127.0.0.1'), true);
  assert.equal(validateBridgeHostHeader('localhost:44444'), true);
  assert.equal(validateBridgeHostHeader('localhost'), true);

  // Malicious or external hosts must be rejected (403)
  assert.equal(validateBridgeHostHeader('evil.com'), false);
  assert.equal(validateBridgeHostHeader('192.168.1.15:44444'), false);
  assert.equal(validateBridgeHostHeader('attacker.xyz:44444'), false);
  assert.equal(validateBridgeHostHeader(undefined), false);
});
