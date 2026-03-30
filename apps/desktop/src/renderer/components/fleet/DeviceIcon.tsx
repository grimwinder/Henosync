import type { DeviceCategory } from "../../types";

interface DeviceIconProps {
  category: DeviceCategory | undefined;
  size?: number;
  color?: string;
}

export default function DeviceIcon({
  category,
  size = 64,
  color = "#4A9EFF",
}: DeviceIconProps) {
  const s = size;
  const c = color;
  const dim = `0 0 ${s} ${s}`;

  switch (category) {
    case "agv":
      // Ground robot / UGV
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Body */}
          <rect
            x={s * 0.15}
            y={s * 0.3}
            width={s * 0.7}
            height={s * 0.35}
            rx={s * 0.06}
            fill={c}
            opacity={0.15}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Wheels */}
          <circle
            cx={s * 0.25}
            cy={s * 0.7}
            r={s * 0.1}
            fill={c}
            opacity={0.3}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          <circle
            cx={s * 0.75}
            cy={s * 0.7}
            r={s * 0.1}
            fill={c}
            opacity={0.3}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Sensor dome */}
          <ellipse
            cx={s * 0.5}
            cy={s * 0.28}
            rx={s * 0.12}
            ry={s * 0.08}
            fill={c}
            opacity={0.25}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          {/* Antenna */}
          <line
            x1={s * 0.5}
            y1={s * 0.2}
            x2={s * 0.5}
            y2={s * 0.08}
            stroke={c}
            strokeWidth={s * 0.025}
            strokeLinecap="round"
          />
          <circle cx={s * 0.5} cy={s * 0.06} r={s * 0.03} fill={c} />
          {/* Eye / sensor */}
          <circle
            cx={s * 0.5}
            cy={s * 0.475}
            r={s * 0.06}
            fill={c}
            opacity={0.5}
          />
          <circle cx={s * 0.5} cy={s * 0.475} r={s * 0.03} fill={c} />
        </svg>
      );

    case "drone":
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Arms */}
          <line
            x1={s * 0.2}
            y1={s * 0.2}
            x2={s * 0.8}
            y2={s * 0.8}
            stroke={c}
            strokeWidth={s * 0.04}
            strokeLinecap="round"
            opacity={0.5}
          />
          <line
            x1={s * 0.8}
            y1={s * 0.2}
            x2={s * 0.2}
            y2={s * 0.8}
            stroke={c}
            strokeWidth={s * 0.04}
            strokeLinecap="round"
            opacity={0.5}
          />
          {/* Motor blobs */}
          {[
            [0.18, 0.18],
            [0.82, 0.18],
            [0.18, 0.82],
            [0.82, 0.82],
          ].map(([x, y], i) => (
            <circle
              key={i}
              cx={s * x}
              cy={s * y}
              r={s * 0.1}
              fill={c}
              opacity={0.2}
              stroke={c}
              strokeWidth={s * 0.025}
            />
          ))}
          {/* Body */}
          <circle
            cx={s * 0.5}
            cy={s * 0.5}
            r={s * 0.14}
            fill={c}
            opacity={0.15}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          <circle cx={s * 0.5} cy={s * 0.5} r={s * 0.06} fill={c} />
        </svg>
      );

    case "boat":
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Hull */}
          <path
            d={`M${s * 0.1} ${s * 0.55} Q${s * 0.5} ${s * 0.8} ${s * 0.9} ${s * 0.55} L${s * 0.85} ${s * 0.42} L${s * 0.15} ${s * 0.42} Z`}
            fill={c}
            opacity={0.15}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Cabin */}
          <rect
            x={s * 0.3}
            y={s * 0.28}
            width={s * 0.4}
            height={s * 0.16}
            rx={s * 0.04}
            fill={c}
            opacity={0.25}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          {/* Mast */}
          <line
            x1={s * 0.5}
            y1={s * 0.28}
            x2={s * 0.5}
            y2={s * 0.1}
            stroke={c}
            strokeWidth={s * 0.025}
            strokeLinecap="round"
          />
          <line
            x1={s * 0.35}
            y1={s * 0.16}
            x2={s * 0.65}
            y2={s * 0.16}
            stroke={c}
            strokeWidth={s * 0.02}
            strokeLinecap="round"
            opacity={0.6}
          />
        </svg>
      );

    default:
      // Generic / sim / unknown
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Outer ring */}
          <circle
            cx={s * 0.5}
            cy={s * 0.5}
            r={s * 0.42}
            stroke={c}
            strokeWidth={s * 0.03}
            opacity={0.2}
          />
          {/* Inner ring */}
          <circle
            cx={s * 0.5}
            cy={s * 0.5}
            r={s * 0.28}
            stroke={c}
            strokeWidth={s * 0.03}
            opacity={0.5}
          />
          {/* Centre dot */}
          <circle cx={s * 0.5} cy={s * 0.5} r={s * 0.1} fill={c} />
          {/* Cardinal spokes */}
          <line
            x1={s * 0.5}
            y1={s * 0.06}
            x2={s * 0.5}
            y2={s * 0.18}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
          />
          <line
            x1={s * 0.5}
            y1={s * 0.82}
            x2={s * 0.5}
            y2={s * 0.94}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
          />
          <line
            x1={s * 0.06}
            y1={s * 0.5}
            x2={s * 0.18}
            y2={s * 0.5}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
          />
          <line
            x1={s * 0.82}
            y1={s * 0.5}
            x2={s * 0.94}
            y2={s * 0.5}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
          />
        </svg>
      );
  }
}
