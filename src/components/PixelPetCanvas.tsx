import React, { useEffect, useRef } from 'react';
import { ExpressionType, HatType, PALETTES } from '../types/clawd';

interface PixelPetCanvasProps {
  paletteId: number;
  hat: HatType;
  fatStage: number; // 0..3
  expression: ExpressionType;
  look: number; // -1, 0, 1
  arms?: 'normal' | 'up' | 'wave1' | 'wave2' | 'tuck';
  legs?: 'stand' | 'walk1' | 'walk2' | 'dangle' | 'tuck';
  mouth?: 'open' | 'chew' | null;
  squash?: number; // -1, 0, 1
  scale?: number;
  isDancing?: boolean;
  className?: string;
}

const GRID_W = 18;
const GRID_H = 13;

export const PixelPetCanvas: React.FC<PixelPetCanvasProps> = ({
  paletteId,
  hat,
  fatStage = 0,
  expression = 'open',
  look = 0,
  arms = 'normal',
  legs = 'stand',
  mouth = null,
  squash = 0,
  scale = 6,
  isDancing = false,
  className = '',
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const s = scale;

    // Palette resolution
    let bodyColor = '#D97757';
    let eyeColor = '#1A1A1A';

    if (paletteId === 9) {
      // Dynamic Rainbow RGB
      const hue = (Date.now() / 2500) % 1;
      const rgb = hsvToRgb(hue, 0.85, 0.95);
      bodyColor = `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
      eyeColor = '#FFFFFF';
    } else {
      const p = PALETTES.find((pal) => pal.id === paletteId) || PALETTES[0];
      bodyColor = p.bodyColor;
      eyeColor = p.eyeColor;
    }

    const blushColor = '#FF5A7A';

    const px = (x0: number, y0: number, x1: number, y1: number, color: string) => {
      ctx.fillStyle = color;
      ctx.fillRect(x0 * s, y0 * s, (x1 - x0) * s, (y1 - y0) * s);
    };

    // 4 стадии полноты «Обжоры»: 0: normal, 1: chubby, 2: fat, 3: balloon
    const widthPad = [0, 1, 2, 3][Math.min(3, Math.max(0, fatStage))];
    let left = Math.max(0, 3 - widthPad);
    let right = Math.min(GRID_W, 15 + widthPad);
    let top = 3;
    const bottom = 10;

    if (squash > 0) {
      left = Math.max(0, left - 1);
      right = Math.min(GRID_W, right + 1);
      top += 2;
    } else if (squash < 0) {
      top -= 1;
    }

    // Ноги
    let legHeights = [2, 2, 2, 2];
    if (legs === 'walk1') legHeights = [1, 2, 1, 2];
    else if (legs === 'walk2') legHeights = [2, 1, 2, 1];
    else if (legs === 'dangle') legHeights = [3, 3, 3, 3];
    else if (legs === 'tuck') legHeights = [1, 1, 1, 1];

    const colCoords = [left + 1, left + 3, right - 4, right - 2];
    colCoords.forEach((col, idx) => {
      px(col, bottom, col + 1, bottom + legHeights[idx], bodyColor);
    });

    // Руки
    const drawArm = (side: number, style: string) => {
      if (style === 'up') {
        if (side < 0) {
          px(left - 2, top - 1, left - 1, top + 3, bodyColor);
          px(left - 1, top + 2, left, top + 3, bodyColor);
        } else {
          px(right + 1, top - 1, right + 2, top + 3, bodyColor);
          px(right, top + 2, right + 1, top + 3, bodyColor);
        }
      } else if (style === 'tuck') {
        if (side < 0) px(left - 1, top + 3, left, top + 5, bodyColor);
        else px(right, top + 3, right + 1, top + 5, bodyColor);
      } else {
        if (side < 0) px(left - 2, top + 3, left, top + 5, bodyColor);
        else px(right, top + 3, right + 2, top + 5, bodyColor);
      }
    };

    let leftArm = arms;
    let rightArm = arms;
    if (arms === 'wave1') {
      leftArm = 'up';
      rightArm = 'normal';
    } else if (arms === 'wave2') {
      leftArm = 'normal';
      rightArm = 'up';
    }
    drawArm(-1, leftArm);
    drawArm(1, rightArm);

    // Тело
    px(left, top, right, bottom, bodyColor);

    // Глаза
    const ey = top + 2;
    const eyeSides = [
      { side: -1, cx: left + 3 + look },
      { side: 1, cx: right - 4 + look },
    ];

    eyeSides.forEach(({ side, cx }) => {
      if (expression === 'blink') {
        px(cx, ey + 1, cx + 1, ey + 2, eyeColor);
      } else if (expression === 'happy') {
        px(cx - 1, ey + 1, cx, ey + 2, eyeColor);
        px(cx, ey, cx + 1, ey + 1, eyeColor);
        px(cx + 1, ey + 1, cx + 2, ey + 2, eyeColor);
      } else if (expression === 'surprised') {
        px(cx, ey - 1, cx + 1, ey + 2, eyeColor);
      } else if (expression === 'dizzy') {
        const spiral = [
          [-1, -1],
          [1, -1],
          [0, 0],
          [-1, 1],
          [1, 1],
        ];
        spiral.forEach(([dx, dy]) => {
          px(cx + dx, ey + dy, cx + dx + 1, ey + dy + 1, eyeColor);
        });
      } else if (expression === 'sleep') {
        px(cx - 1, ey + 1, cx + 2, ey + 2, eyeColor);
      } else if (expression === 'money') {
        px(cx, ey - 1, cx + 1, ey + 2, '#22C55E');
        px(cx - 1, ey, cx + 2, ey + 1, '#22C55E');
      } else if (expression === 'angry') {
        px(cx, ey, cx + 1, ey + 2, eyeColor);
        const brow = side < 0 ? cx - 1 : cx + 1;
        px(brow, ey - 1, brow + 1, ey, eyeColor);
      } else {
        px(cx, ey, cx + 1, ey + 2, eyeColor);
      }

      // Румянец при счастье или на стадиях полноты
      if (expression === 'happy' || fatStage >= 1) {
        const bx = side < 0 ? cx - 2 : cx + 1;
        px(bx, ey + 2, bx + 2, ey + 3, blushColor);
      }
    });

    // Рот
    if (mouth) {
      const mx = Math.floor((left + right) / 2);
      const my = ey + 2;
      if (mouth === 'open') {
        px(mx - 1, my, mx + 1, bottom - 1, eyeColor);
      } else {
        px(mx - 1, my, mx + 1, my + 1, eyeColor);
      }
    }

    // 11 Шапок
    if (hat.includes('Наушники') || (isDancing && !hat.includes('Корона'))) {
      px(left + 2, top - 2, right - 2, top - 1, '#2A2A2A');
      px(left - 1, top, left, top + 4, '#EF4444');
      px(right, top, right + 1, top + 4, '#EF4444');
    } else if (hat.includes('Корона')) {
      const gold = '#FACC15';
      px(left + 2, top - 2, right - 2, top, gold);
      px(left + 2, top - 3, left + 3, top - 2, gold);
      px(Math.floor((left + right) / 2), top - 3, Math.floor((left + right) / 2) + 1, top - 2, gold);
      px(right - 3, top - 3, right - 2, top - 2, gold);
    } else if (hat.includes('Шерлок')) {
      const brown = '#8D6E63';
      px(left - 1, top - 1, right + 1, top, brown);
      px(left + 2, top - 3, right - 2, top - 1, brown);
    } else if (hat.includes('Ночной колпак')) {
      const blue = '#4F46E5';
      px(left + 2, top - 3, right - 1, top, blue);
      px(right - 1, top - 2, right + 1, top - 1, '#FFFFFF');
    } else if (hat.includes('Кошачьи ушки')) {
      px(left + 1, top - 2, left + 3, top, bodyColor);
      px(right - 3, top - 2, right - 1, top, bodyColor);
      px(left + 2, top - 1, left + 3, top, '#F472B6');
      px(right - 2, top - 1, right - 1, top, '#F472B6');
    } else if (hat.includes('Цилиндр')) {
      px(left, top - 1, right, top, '#111827');
      px(left + 3, top - 4, right - 3, top - 1, '#1F2937');
      px(right - 3, ey, right - 1, ey + 2, '#FACC15'); // монокль
    } else if (hat.includes('Каска')) {
      px(left - 1, top - 1, right + 1, top, '#F59E0B');
      px(left + 2, top - 3, right - 2, top - 1, '#FBBF24');
    } else if (hat.includes('Thug')) {
      px(left + 1, ey, right - 1, ey + 2, '#111111');
      px(left + 3, ey + 1, left + 4, ey + 2, '#FFFFFF');
      px(right - 4, ey + 1, right - 3, ey + 2, '#FFFFFF');
    } else if (hat.includes('Мага')) {
      px(left, top - 1, right, top, '#4C1D95');
      px(left + 4, top - 4, right - 4, top - 1, '#6D28D9');
      px(Math.floor((left + right) / 2), top - 5, Math.floor((left + right) / 2) + 1, top - 4, '#FACC15');
    } else if (hat.includes('Кепка')) {
      px(left, top - 2, right - 1, top, '#DC2626');
      px(right - 1, top - 1, right + 3, top, '#B91C1C'); // козырек назад
    }
  }, [paletteId, hat, fatStage, expression, look, arms, legs, mouth, squash, scale, isDancing]);

  return (
    <canvas
      ref={canvasRef}
      width={GRID_W * scale}
      height={GRID_H * scale}
      className={`inline-block ${className}`}
      style={{ imageRendering: 'pixelated' }}
    />
  );
};

function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - s * f);
  const t = v * (1 - s * (1 - f));
  let r = 0;
  let g = 0;
  let b = 0;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    case 5: r = v; g = p; b = q; break;
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}
