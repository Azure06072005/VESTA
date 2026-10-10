import React, { useMemo, useState } from 'react';

export interface TreemapNode {
  id: string;
  name: string;
  value: number; // Traded value or market cap for size
  pctChange: number; // For 3 main colors: green, red, black-orange
  group?: string; // Optional parent group/category (e.g., Financials, Industrials, etc.)
  subLabel?: string;
  details?: {
    adv?: number;
    dec?: number;
    pe?: number;
    pb?: number;
    turnover?: number;
    price?: number;
    topStocks?: string[];
  };
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface LayoutItem extends TreemapNode {
  rect: Rect;
}

interface GroupLayout {
  groupName: string;
  rect: Rect;
  totalValue: number;
  avgPctChange: number;
  children: LayoutItem[];
}

interface FoamTreeTreemapProps {
  items: TreemapNode[];
  width?: number | string;
  height?: number;
  onSelect?: (item: TreemapNode) => void;
  sizeLabel?: string;
  emptyMessage?: string;
}

/**
 * Classic Squarified Treemap Layout Algorithm (Bruls, Huizing, van Wijk)
 * Computes rectangles with aspect ratios close to 1:1 squares.
 */
function computeSquarifiedLayout<T extends { value: number }>(
  nodes: T[],
  x: number,
  y: number,
  w: number,
  h: number
): (T & { rect: Rect })[] {
  if (!nodes || nodes.length === 0 || w <= 0 || h <= 0) return [];

  const validNodes = nodes
    .filter((n) => Number.isFinite(n.value) && n.value > 0)
    .sort((a, b) => b.value - a.value);

  if (validNodes.length === 0) return [];

  const totalValue = validNodes.reduce((sum, n) => sum + n.value, 0);
  const totalArea = w * h;

  const normalizedNodes = validNodes.map((n) => ({
    ...n,
    area: (n.value / totalValue) * totalArea,
  }));

  const layout: (T & { rect: Rect })[] = [];

  function worstRatio(row: number[], side: number): number {
    const s = row.reduce((a, b) => a + b, 0);
    if (s === 0 || side === 0) return Infinity;
    const s2 = s * s;
    const side2 = side * side;
    let max = -Infinity;
    let min = Infinity;
    for (const area of row) {
      if (area > max) max = area;
      if (area < min) min = area;
    }
    return Math.max((side2 * max) / s2, s2 / (side2 * min));
  }

  function layoutRow(
    row: typeof normalizedNodes,
    rx: number,
    ry: number,
    rw: number,
    isVertical: boolean
  ): (T & { rect: Rect })[] {
    const s = row.reduce((sum, item) => sum + item.area, 0);
    const rowThickness = s / rw;
    let offset = 0;
    const result: (T & { rect: Rect })[] = [];

    for (const item of row) {
      const itemLength = item.area / rowThickness;
      if (isVertical) {
        result.push({
          ...item,
          rect: {
            x: rx + offset,
            y: ry,
            w: Math.max(0, itemLength),
            h: Math.max(0, rowThickness),
          },
        });
      } else {
        result.push({
          ...item,
          rect: {
            x: rx,
            y: ry + offset,
            w: Math.max(0, rowThickness),
            h: Math.max(0, itemLength),
          },
        });
      }
      offset += itemLength;
    }
    return result;
  }

  function squarify(
    children: typeof normalizedNodes,
    currentRow: typeof normalizedNodes,
    curX: number,
    curY: number,
    curW: number,
    curH: number
  ) {
    if (children.length === 0) {
      if (currentRow.length > 0) {
        const isVert = curW <= curH;
        layout.push(...layoutRow(currentRow, curX, curY, isVert ? curW : curH, isVert));
      }
      return;
    }

    const item = children[0];
    const isVert = curW <= curH;
    const side = isVert ? curW : curH;

    const rowWithItem = [...currentRow, item];
    const currentWorst = worstRatio(currentRow.map((r) => r.area), side);
    const newWorst = worstRatio(rowWithItem.map((r) => r.area), side);

    if (currentRow.length === 0 || newWorst <= currentWorst) {
      squarify(children.slice(1), rowWithItem, curX, curY, curW, curH);
    } else {
      const placed = layoutRow(currentRow, curX, curY, side, isVert);
      layout.push(...placed);

      const rowArea = currentRow.reduce((sum, r) => sum + r.area, 0);
      const rowThickness = rowArea / side;

      if (isVert) {
        squarify(children, [], curX, curY + rowThickness, curW, Math.max(0, curH - rowThickness));
      } else {
        squarify(children, [], curX + rowThickness, curY, Math.max(0, curW - rowThickness), curH);
      }
    }
  }

  squarify(normalizedNodes, [], x, y, w, h);
  return layout;
}

/**
 * 3 Main Colors for Percentage Change:
 * 1. Green (#22A366 / #16a34a / #00a651) for positive %
 * 2. Red (#D6483F / #dc2626 / #e53935) for negative %
 * 3. Black-Orange (#D97706 / #b45309) for zero / neutral %
 */
function getNodeColor(pct: number): { bg: string; border: string; text: string } {
  if (pct > 0) {
    // Punchy FoamTree Green
    if (pct >= 2.0) return { bg: '#00b84f', border: '#22c55e', text: '#000000' };
    if (pct >= 0.5) return { bg: '#00a651', border: '#4ade80', text: '#000000' };
    return { bg: '#22A366', border: '#86efac', text: '#000000' };
  } else if (pct < 0) {
    // Punchy FoamTree Red
    if (pct <= -2.0) return { bg: '#dc2626', border: '#ef4444', text: '#000000' };
    if (pct <= -0.5) return { bg: '#e53935', border: '#f87171', text: '#000000' };
    return { bg: '#D6483F', border: '#fca5a5', text: '#000000' };
  } else {
    // Black-Orange / Reference (#D97706 / #b45309)
    return { bg: '#b45309', border: '#f59e0b', text: '#ffffff' };
  }
}

export const FoamTreeTreemap: React.FC<FoamTreeTreemapProps> = ({
  items,
  height = 440,
  onSelect,
  sizeLabel = 'GTGD (Tỷ)',
  emptyMessage = 'Không có dữ liệu FoamTree',
}) => {
  const [containerWidth, setContainerWidth] = useState<number>(850);
  const [hoveredNode, setHoveredNode] = useState<LayoutItem | null>(null);

  const containerRef = React.useCallback((node: HTMLDivElement | null) => {
    if (node !== null) {
      setContainerWidth(node.getBoundingClientRect().width || 850);
    }
  }, []);

  React.useEffect(() => {
    const handleResize = () => {
      const el = document.getElementById('foamtree-container');
      if (el) {
        setContainerWidth(el.getBoundingClientRect().width || 850);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Check if items have groups
  const hasGroups = useMemo(() => {
    return items.some((item) => !!item.group && item.group.trim().length > 0);
  }, [items]);

  // Compute hierarchical layout or flat layout
  const { groupLayouts, flatLayouts } = useMemo(() => {
    const margin = 4;
    const usableW = Math.max(100, containerWidth - margin * 2);
    const usableH = Math.max(100, height - margin * 2);

    if (hasGroups) {
      // Group items
      const map = new Map<string, TreemapNode[]>();
      for (const item of items) {
        const gName = item.group || 'Khác';
        if (!map.has(gName)) map.set(gName, []);
        map.get(gName)!.push(item);
      }

      // Compute group summaries
      const groupSummaries = Array.from(map.entries()).map(([gName, gItems]) => {
        const totalVal = gItems.reduce((acc, i) => acc + (i.value > 0 ? i.value : 10), 0);
        const weightedPct =
          totalVal > 0
            ? gItems.reduce((acc, i) => acc + i.pctChange * (i.value > 0 ? i.value : 10), 0) / totalVal
            : 0;
        return {
          groupName: gName,
          value: totalVal,
          avgPctChange: weightedPct,
          rawItems: gItems,
        };
      });

      // Squarify top-level groups
      const placedGroups = computeSquarifiedLayout(
        groupSummaries,
        margin,
        margin,
        usableW,
        usableH
      );

      // Inside each group, place its children
      const result: GroupLayout[] = placedGroups.map((g) => {
        const headerHeight = 22;
        const innerPad = 3;
        const innerX = g.rect.x + innerPad;
        const innerY = g.rect.y + headerHeight;
        const innerW = Math.max(0, g.rect.w - innerPad * 2);
        const innerH = Math.max(0, g.rect.h - headerHeight - innerPad);

        const children = computeSquarifiedLayout(
          g.rawItems,
          innerX,
          innerY,
          innerW,
          innerH
        );

        return {
          groupName: g.groupName,
          rect: g.rect,
          totalValue: g.value,
          avgPctChange: g.avgPctChange,
          children: children as LayoutItem[],
        };
      });

      return { groupLayouts: result, flatLayouts: [] };
    } else {
      // Flat layout
      const placed = computeSquarifiedLayout(items, margin, margin, usableW, usableH);
      return { groupLayouts: [], flatLayouts: placed as LayoutItem[] };
    }
  }, [items, hasGroups, containerWidth, height]);

  if (!items || items.length === 0) {
    return (
      <div
        style={{
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--cream3)',
          fontFamily: 'var(--sans)',
          fontSize: '12px',
        }}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div
      id="foamtree-container"
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height,
        background: '#04040a',
        borderRadius: 'var(--rad)',
        overflow: 'hidden',
        border: '0.5px solid var(--border)',
        userSelect: 'none',
      }}
    >
      <svg width={containerWidth} height={height} style={{ display: 'block' }}>
        {/* HIERARCHICAL GROUPS RENDERING */}
        {hasGroups &&
          groupLayouts.map((grp) => {
            const { x, y, w, h } = grp.rect;
            if (w < 10 || h < 10) return null;

            return (
              <g key={`grp-${grp.groupName}`}>
                {/* Group Container Border and Header Background */}
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  rx={4}
                  ry={4}
                  fill="rgba(16, 16, 28, 0.85)"
                  stroke="rgba(255, 255, 255, 0.12)"
                  strokeWidth={1}
                />

                {/* Group Title Header Bar */}
                <text
                  x={x + w / 2}
                  y={y + 14}
                  textAnchor="middle"
                  fill="#c8c4bc"
                  style={{
                    fontFamily: "var(--sans), 'Syne', sans-serif",
                    fontWeight: 700,
                    fontSize: w > 100 ? '11px' : '9px',
                    letterSpacing: '0.02em',
                    pointerEvents: 'none',
                  }}
                >
                  {w < 70 && grp.groupName.length > 8
                    ? `${grp.groupName.slice(0, 7)}…`
                    : grp.groupName}
                </text>

                {/* Children Cells inside Group */}
                {grp.children.map((child) => {
                  const cx = child.rect.x;
                  const cy = child.rect.y;
                  const cw = child.rect.w;
                  const ch = child.rect.h;

                  if (cw < 4 || ch < 4) return null;

                  const isHovered = hoveredNode?.id === child.id;
                  const colors = getNodeColor(child.pctChange);
                  const isSmall = cw < 60 || ch < 45;
                  const isTiny = cw < 36 || ch < 26;

                  // Inner cell padding
                  const pad = 1.5;
                  const rw = Math.max(0, cw - pad * 2);
                  const rh = Math.max(0, ch - pad * 2);

                  const sign = child.pctChange > 0 ? '+' : '';
                  const pctStr = `${sign}${child.pctChange.toFixed(2)}%`;

                  // Smart truncated display name fitting within cell width
                  const maxChars = Math.max(3, Math.floor(rw / (isSmall ? 7 : 9)));
                  let displayName = child.name;
                  if (displayName.length > maxChars) {
                    displayName = child.id && child.id.length <= maxChars ? child.id : `${displayName.slice(0, Math.max(2, maxChars - 1))}…`;
                  }

                  const clipId = `clip-${child.id}-${Math.round(cx)}-${Math.round(cy)}`;

                  return (
                    <g
                      key={child.id}
                      transform={`translate(${cx + pad}, ${cy + pad})`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSelect && onSelect(child)}
                      onMouseEnter={() => setHoveredNode(child)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      <defs>
                        <clipPath id={clipId}>
                          <rect width={rw} height={rh} rx={3} ry={3} />
                        </clipPath>
                      </defs>

                      <rect
                        width={rw}
                        height={rh}
                        rx={3}
                        ry={3}
                        fill={colors.bg}
                        stroke={isHovered ? '#ffffff' : colors.border}
                        strokeWidth={isHovered ? 2 : 0.6}
                        opacity={isHovered ? 1 : 0.94}
                        style={{
                          transition: 'all 0.12s ease',
                          filter: isHovered ? 'brightness(1.2)' : 'none',
                        }}
                      />

                      {/* Cell Content with SVG Clipping */}
                      <g clipPath={`url(#${clipId})`}>
                        {isTiny ? (
                          <text
                            x={rw / 2}
                            y={rh / 2}
                            textAnchor="middle"
                            dominantBaseline="central"
                            fill={colors.text}
                            style={{
                              fontFamily: "var(--sans), 'Syne', sans-serif",
                              fontWeight: 800,
                              fontSize: '10px',
                              pointerEvents: 'none',
                            }}
                          >
                            …
                          </text>
                        ) : (
                          <>
                            <text
                              x={rw / 2}
                              y={rh / 2 - (isSmall ? 0 : 9)}
                              textAnchor="middle"
                              dominantBaseline="central"
                              fill={colors.text}
                              style={{
                                fontFamily: "var(--sans), 'Syne', sans-serif",
                                fontWeight: 800,
                                fontSize: isSmall
                                  ? '9px'
                                  : rw > 130
                                  ? '14px'
                                  : '11px',
                                letterSpacing: '-0.01em',
                                pointerEvents: 'none',
                              }}
                            >
                              {displayName}
                            </text>

                            {!isSmall && (
                              <text
                                x={rw / 2}
                                y={rh / 2 + 13}
                                textAnchor="middle"
                                dominantBaseline="central"
                                fill={colors.text}
                                style={{
                                  fontFamily: "var(--mono), 'Syne Mono', monospace",
                                  fontWeight: 800,
                                  fontSize: rw > 130 ? '13px' : '11px',
                                  pointerEvents: 'none',
                                }}
                              >
                                {pctStr}
                              </text>
                            )}
                          </>
                        )}
                      </g>
                    </g>
                  );
                })}
              </g>
            );
          })}

        {/* FLAT LAYOUT RENDERING (if no groups) */}
        {!hasGroups &&
          flatLayouts.map((item) => {
            const { x, y, w, h } = item.rect;
            if (w < 4 || h < 4) return null;

            const isHovered = hoveredNode?.id === item.id;
            const colors = getNodeColor(item.pctChange);
            const isSmall = w < 60 || h < 45;
            const isTiny = w < 36 || h < 26;

            const pad = 2;
            const rw = Math.max(0, w - pad * 2);
            const rh = Math.max(0, h - pad * 2);
            const sign = item.pctChange > 0 ? '+' : '';
            const pctStr = `${sign}${item.pctChange.toFixed(2)}%`;

            return (
              <g
                key={item.id}
                transform={`translate(${x + pad}, ${y + pad})`}
                style={{ cursor: 'pointer' }}
                onClick={() => onSelect && onSelect(item)}
                onMouseEnter={() => setHoveredNode(item)}
                onMouseLeave={() => setHoveredNode(null)}
              >
                <rect
                  width={rw}
                  height={rh}
                  rx={3}
                  ry={3}
                  fill={colors.bg}
                  stroke={isHovered ? '#ffffff' : colors.border}
                  strokeWidth={isHovered ? 2 : 0.8}
                  opacity={isHovered ? 1 : 0.94}
                  style={{
                    transition: 'all 0.12s ease',
                    filter: isHovered ? 'brightness(1.2)' : 'none',
                  }}
                />

                {isTiny ? (
                  <text
                    x={rw / 2}
                    y={rh / 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill={colors.text}
                    style={{
                      fontFamily: "var(--sans), 'Syne', sans-serif",
                      fontWeight: 800,
                      fontSize: '10px',
                      pointerEvents: 'none',
                    }}
                  >
                    …
                  </text>
                ) : (
                  <>
                    <text
                      x={rw / 2}
                      y={rh / 2 - (isSmall ? 0 : 9)}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill={colors.text}
                      style={{
                        fontFamily: "var(--sans), 'Syne', sans-serif",
                        fontWeight: 800,
                        fontSize: isSmall ? '10px' : rw > 120 ? '14px' : '11px',
                        pointerEvents: 'none',
                      }}
                    >
                      {rw < 70 && item.name.length > 8 ? item.id : item.name}
                    </text>

                    {!isSmall && (
                      <text
                        x={rw / 2}
                        y={rh / 2 + 13}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill={colors.text}
                        style={{
                          fontFamily: "var(--mono), 'Syne Mono', monospace",
                          fontWeight: 800,
                          fontSize: rw > 120 ? '13px' : '11px',
                          pointerEvents: 'none',
                        }}
                      >
                        {pctStr}
                      </text>
                    )}
                  </>
                )}
              </g>
            );
          })}
      </svg>

      {/* FoamTree Icon & Watermark in Bottom-Right Corner (Matches screenshot) */}
      <div
        style={{
          position: 'absolute',
          bottom: '8px',
          right: '8px',
          background: 'rgba(255, 255, 255, 0.92)',
          borderRadius: '4px',
          padding: '3px 6px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          boxShadow: '0 2px 8px rgba(0,0,0,0.5)',
          pointerEvents: 'none',
          opacity: 0.88,
          zIndex: 10,
        }}
      >
        {/* Voronoi / Honeycomb SVG icon */}
        <svg width="24" height="20" viewBox="0 0 24 20" fill="none">
          <path d="M12 2L16 5L15 9L11 8L9 4L12 2Z" fill="#D6483F" />
          <path d="M16 5L20 4L22 8L18 10L15 9L16 5Z" fill="#b91c1c" />
          <path d="M18 10L22 11L21 15L17 14L18 10Z" fill="#ef4444" />
          <path d="M11 8L15 9L14 14L10 13L11 8Z" fill="#D97706" />
          <path d="M9 4L11 8L7 11L4 8L5 5L9 4Z" fill="#22A366" />
          <path d="M7 11L10 13L9 17L5 16L4 12L7 11Z" fill="#15803d" />
          <path d="M10 13L14 14L13 18L9 17L10 13Z" fill="#b45309" />
          <path d="M14 14L17 14L16 18L13 18L14 14Z" fill="#D6483F" />
        </svg>
        <span
          style={{
            fontFamily: "var(--sans), 'Syne', sans-serif",
            fontWeight: 800,
            fontSize: '8px',
            color: '#111827',
            letterSpacing: '0.02em',
            marginTop: '1px',
          }}
        >
          FoamTree
        </span>
      </div>

      {/* Floating Tooltip */}
      {hoveredNode && (
        <div
          style={{
            position: 'absolute',
            pointerEvents: 'none',
            left: Math.min(
              containerWidth - 230,
              Math.max(10, hoveredNode.rect.x + hoveredNode.rect.w / 2 - 100)
            ),
            top: Math.max(10, hoveredNode.rect.y - 75),
            zIndex: 100,
            background: 'rgba(10, 10, 22, 0.96)',
            border: '1px solid var(--teal)',
            borderRadius: 'var(--rad)',
            padding: '8px 12px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.7)',
            minWidth: '190px',
            fontSize: '11px',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '4px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--sans)',
                fontWeight: 800,
                color: 'var(--cream)',
                fontSize: '12px',
              }}
            >
              {hoveredNode.name}
            </span>
            <span
              className={`mono tabular ${
                hoveredNode.pctChange > 0
                  ? 'txt-up'
                  : hoveredNode.pctChange < 0
                  ? 'txt-down'
                  : 'txt-ref'
              }`}
              style={{ fontWeight: 800 }}
            >
              {hoveredNode.pctChange > 0 ? '+' : ''}
              {hoveredNode.pctChange.toFixed(2)}%
            </span>
          </div>

          {hoveredNode.group && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                color: 'var(--cream3)',
                marginBottom: '3px',
              }}
            >
              <span>Nhóm ngành / Group:</span>
              <span style={{ color: 'var(--cream2)', fontWeight: 600 }}>
                {hoveredNode.group}
              </span>
            </div>
          )}

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              color: 'var(--cream3)',
              marginBottom: '2px',
            }}
          >
            <span>{sizeLabel}:</span>
            <span className="mono tabular" style={{ color: 'var(--cream)', fontWeight: 700 }}>
              {hoveredNode.value >= 1e9
                ? `${(hoveredNode.value / 1e9).toFixed(1)} Tỷ / Bn`
                : `${hoveredNode.value.toLocaleString('vi-VN')}`}
            </span>
          </div>

          {hoveredNode.details?.topStocks && (
            <div
              style={{
                marginTop: '4px',
                borderTop: '0.5px solid var(--border)',
                paddingTop: '4px',
                display: 'flex',
                gap: '4px',
                flexWrap: 'wrap',
              }}
            >
              <span style={{ color: 'var(--cream3)' }}>Mã dẫn dắt:</span>
              {hoveredNode.details.topStocks.map((s) => (
                <span
                  key={s}
                  className="badge"
                  style={{
                    background: 'var(--bg4)',
                    color: 'var(--teal)',
                    fontWeight: 700,
                    fontSize: '9px',
                    padding: '1px 4px',
                  }}
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
