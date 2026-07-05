"use client";

import dynamic from "next/dynamic";
import type { Data, Layout } from "plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export type PlotlyFigure = {
  data: Data[];
  layout: Partial<Layout>;
};

export default function PlotlyChart({ figure }: { figure: PlotlyFigure }) {
  return (
    <Plot
      data={figure.data}
      layout={{ ...figure.layout, autosize: true, margin: { t: 30, r: 20, b: 40, l: 50 } }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "360px" }}
      useResizeHandler
    />
  );
}
