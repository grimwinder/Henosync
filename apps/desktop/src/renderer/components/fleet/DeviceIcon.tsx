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
      // Quadcopter
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
          {/* Motor hubs */}
          {(
            [
              [0.18, 0.18],
              [0.82, 0.18],
              [0.18, 0.82],
              [0.82, 0.82],
            ] as [number, number][]
          ).map(([x, y], i) => (
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

    case "plane":
      // Fixed-wing UAV
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Fuselage */}
          <ellipse
            cx={s * 0.5}
            cy={s * 0.5}
            rx={s * 0.38}
            ry={s * 0.07}
            fill={c}
            opacity={0.15}
            stroke={c}
            strokeWidth={s * 0.028}
          />
          {/* Main wings */}
          <path
            d={`M${s * 0.42} ${s * 0.5} L${s * 0.1} ${s * 0.38} L${s * 0.14} ${s * 0.52} Z`}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
            strokeLinejoin="round"
          />
          <path
            d={`M${s * 0.42} ${s * 0.5} L${s * 0.1} ${s * 0.62} L${s * 0.14} ${s * 0.48} Z`}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
            strokeLinejoin="round"
          />
          {/* Tail fin */}
          <path
            d={`M${s * 0.78} ${s * 0.5} L${s * 0.88} ${s * 0.34} L${s * 0.84} ${s * 0.5} Z`}
            fill={c}
            opacity={0.25}
            stroke={c}
            strokeWidth={s * 0.025}
            strokeLinejoin="round"
          />
          {/* Horizontal stabiliser */}
          <path
            d={`M${s * 0.76} ${s * 0.5} L${s * 0.6} ${s * 0.42} L${s * 0.62} ${s * 0.5} Z`}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.022}
            strokeLinejoin="round"
          />
          <path
            d={`M${s * 0.76} ${s * 0.5} L${s * 0.6} ${s * 0.58} L${s * 0.62} ${s * 0.5} Z`}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.022}
            strokeLinejoin="round"
          />
          {/* Nose dot */}
          <circle cx={s * 0.13} cy={s * 0.5} r={s * 0.03} fill={c} />
        </svg>
      );

    case "boat":
      // Surface vessel / USV
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

    case "rov":
      // Underwater remotely operated vehicle
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Body frame */}
          <rect
            x={s * 0.18}
            y={s * 0.3}
            width={s * 0.64}
            height={s * 0.38}
            rx={s * 0.08}
            fill={c}
            opacity={0.12}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Top thrusters */}
          <ellipse
            cx={s * 0.3}
            cy={s * 0.22}
            rx={s * 0.09}
            ry={s * 0.05}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          <ellipse
            cx={s * 0.7}
            cy={s * 0.22}
            rx={s * 0.09}
            ry={s * 0.05}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          <line
            x1={s * 0.3}
            y1={s * 0.27}
            x2={s * 0.3}
            y2={s * 0.3}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          <line
            x1={s * 0.7}
            y1={s * 0.27}
            x2={s * 0.7}
            y2={s * 0.3}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          {/* Side thrusters */}
          <ellipse
            cx={s * 0.12}
            cy={s * 0.49}
            rx={s * 0.05}
            ry={s * 0.09}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          <ellipse
            cx={s * 0.88}
            cy={s * 0.49}
            rx={s * 0.05}
            ry={s * 0.09}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          {/* Camera eye */}
          <circle
            cx={s * 0.32}
            cy={s * 0.49}
            r={s * 0.06}
            fill={c}
            opacity={0.3}
            stroke={c}
            strokeWidth={s * 0.025}
          />
          <circle cx={s * 0.32} cy={s * 0.49} r={s * 0.03} fill={c} />
          {/* Tether */}
          <line
            x1={s * 0.5}
            y1={s * 0.3}
            x2={s * 0.5}
            y2={s * 0.1}
            stroke={c}
            strokeWidth={s * 0.022}
            strokeDasharray={`${s * 0.04} ${s * 0.03}`}
            strokeLinecap="round"
            opacity={0.5}
          />
        </svg>
      );

    case "arm":
      // Robotic manipulator arm
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          {/* Base */}
          <ellipse
            cx={s * 0.5}
            cy={s * 0.82}
            rx={s * 0.22}
            ry={s * 0.08}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Lower arm */}
          <line
            x1={s * 0.5}
            y1={s * 0.82}
            x2={s * 0.32}
            y2={s * 0.52}
            stroke={c}
            strokeWidth={s * 0.06}
            strokeLinecap="round"
            opacity={0.4}
          />
          {/* Elbow joint */}
          <circle
            cx={s * 0.32}
            cy={s * 0.52}
            r={s * 0.07}
            fill={c}
            opacity={0.2}
            stroke={c}
            strokeWidth={s * 0.03}
          />
          {/* Upper arm */}
          <line
            x1={s * 0.32}
            y1={s * 0.52}
            x2={s * 0.62}
            y2={s * 0.26}
            stroke={c}
            strokeWidth={s * 0.05}
            strokeLinecap="round"
            opacity={0.5}
          />
          {/* Wrist joint */}
          <circle
            cx={s * 0.62}
            cy={s * 0.26}
            r={s * 0.055}
            fill={c}
            opacity={0.25}
            stroke={c}
            strokeWidth={s * 0.028}
          />
          {/* Gripper fingers */}
          <line
            x1={s * 0.62}
            y1={s * 0.21}
            x2={s * 0.72}
            y2={s * 0.13}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
            opacity={0.7}
          />
          <line
            x1={s * 0.62}
            y1={s * 0.21}
            x2={s * 0.54}
            y2={s * 0.12}
            stroke={c}
            strokeWidth={s * 0.03}
            strokeLinecap="round"
            opacity={0.7}
          />
        </svg>
      );

    default:
      // Generic / sim / unknown — compass rose
      return (
        <svg width={s} height={s} viewBox={dim} fill="none">
          <circle
            cx={s * 0.5}
            cy={s * 0.5}
            r={s * 0.42}
            stroke={c}
            strokeWidth={s * 0.03}
            opacity={0.2}
          />
          <circle
            cx={s * 0.5}
            cy={s * 0.5}
            r={s * 0.28}
            stroke={c}
            strokeWidth={s * 0.03}
            opacity={0.5}
          />
          <circle cx={s * 0.5} cy={s * 0.5} r={s * 0.1} fill={c} />
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
