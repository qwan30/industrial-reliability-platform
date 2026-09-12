import type { CSSProperties } from "react";

const paths = {
  cube: "M12 2 3 7v10l9 5 9-5V7L12 2Z M3 7l9 5 9-5 M12 12v10 M7.5 4.5l9 5v5",
  search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  compressor:
    "M4 8h13v11H4z M7 8V5h7v3 M17 11h3v5h-3 M7 12v4 M11 12v4 M3 21h15",
  tank: "M7 5c0-4 10-4 10 0v13c0 4-10 4-10 0V5Z M7 6h10 M7 17h10 M9 21v1 M15 21v1",
  valve: "M3 8l9 5-9 5V8Z M21 8l-9 5 9 5V8Z M12 13V4 M8 4h8",
  load: "M3 21V10l6 4V8l6 5V4h5v17H3Z M7 17v1 M12 17v1 M17 17v1",
  pipe: "M3 5h11v10h7 M3 9h7v10h11 M3 3v8 M21 13v8",
  sensor: "M4 15a9 9 0 1 1 16 0 M6 20h12 M12 11l4-4 M12 11v2",
  topology: "M9 3h6v5H9z M2 17h6v5H2z M16 17h6v5h-6z M12 8v5 M5 17v-4h14v4",
  home: "M3 10 12 3l9 7 M5 9v12h5v-7h4v7h5V9",
  orbit: "M12 3a9 9 0 1 1-9 9 M3 3v6h6 M12 9v6 M9 12h6",
  walk: "M13 8l-3 5 4 3v6 M10 13l-3 8 M13 8l3 5h4 M8 8l-4 4 M15 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  chevron: "m8 4 8 8-8 8",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12 M6 18 18 6",
  help: "M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3 M12 17h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  inspect: "M4 5h16 M4 12h16 M4 19h16 M8 3v4 M16 10v4 M10 17v4",
} as const;
export type LabIconName = keyof typeof paths;
export function LabIcon({
  name,
  size = 18,
  style,
}: {
  name: LabIconName;
  size?: number;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      <path d={paths[name]} />
    </svg>
  );
}
