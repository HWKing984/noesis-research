import React from 'react';

/** NOESIS 的螺线标（路径逐字照抄 ChatArea.jsx 的 welcome-glyph）。 */
export const SPIRAL_PATH =
  'M 2.4,24.25 A 16.5,16.5 0 0 1 18.9,7.75 A 10.2,10.2 0 0 1 29.1,17.95 A 6.3,6.3 0 0 1 22.8,24.25 A 3.9,3.9 0 0 1 18.9,20.35 A 2.4,2.4 0 0 1 21.3,17.95 A 1.5,1.5 0 0 1 22.8,19.45';

export default function SpiralMark({ size = 48, strokeWidth = 1.8 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d={SPIRAL_PATH} stroke="var(--accent)" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  );
}
