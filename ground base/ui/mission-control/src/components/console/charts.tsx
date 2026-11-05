export function LineChart({
  values,
  min,
  max,
  caption,
  markAt,
  yTicks,
}: {
  values: number[];
  min: number;
  max: number;
  caption: string;
  markAt?: number;
  yTicks: number[];
}) {
  const width = 640;
  const height = 220;
  const pad = 28;
  const x = (index: number) => pad + (index / Math.max(1, values.length - 1)) * (width - pad * 2);
  const y = (value: number) => pad + (1 - (value - min) / (max - min)) * (height - pad * 2);
  const d = values.map((value, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-52 w-full" role="img" aria-label={caption}>
      {yTicks.map((tick) => (
        <g key={tick}>
          <line x1={pad} x2={width - 8} y1={y(tick)} y2={y(tick)} stroke="#D6E4F5" />
          <text x={4} y={y(tick) + 4} fontSize="11" fill="#66768F">
            {tick}
          </text>
        </g>
      ))}
      {markAt !== undefined ? (
        <>
          <rect x={pad} y={pad} width={Math.max(0, x(markAt) - pad)} height={height - pad * 2} fill="#16A879" opacity="0.12" />
          <rect x={x(markAt)} y={pad} width={Math.max(0, width - pad - x(markAt))} height={height - pad * 2} fill="#E85A67" opacity="0.12" />
          <text x={pad + 8} y={pad + 16} fontSize="11" fill="#16A879">Beacon epoch 4 · hold stable</text>
          <text x={x(markAt) + 8} y={pad + 16} fontSize="11" fill="#E85A67">Drone motion · hold invalidated</text>
        </>
      ) : null}
      <path d={d} fill="none" stroke="#1769FF" strokeWidth="3" />
      {markAt !== undefined ? (
        <line x1={x(markAt)} x2={x(markAt)} y1={pad} y2={height - pad} stroke="#E85A67" strokeDasharray="4 4" />
      ) : null}
      {[0, 10, 20, 30, 40, 50, 60].map((tick) => (
        <text key={tick} x={pad + (tick / 60) * (width - pad * 2)} y={height - 8} fontSize="11" fill="#66768F" textAnchor="middle">
          {tick}
        </text>
      ))}
    </svg>
  );
}
