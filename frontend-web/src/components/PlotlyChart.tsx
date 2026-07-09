"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import dynamic from "next/dynamic";
import type { Data, Layout } from "plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export type PlotlyFigure = {
  data: Data[];
  layout: Partial<Layout>;
};

export type PlotlyChartHandle = {
  downloadPng: (filename: string) => Promise<void>;
};

const PlotlyChart = forwardRef<PlotlyChartHandle, { figure: PlotlyFigure }>(function PlotlyChart(
  { figure },
  ref
) {
  const graphDivRef = useRef<HTMLElement | null>(null);

  useImperativeHandle(ref, () => ({
    async downloadPng(filename: string) {
      const graphDiv = graphDivRef.current;
      if (!graphDiv) return;
      const Plotly = (await import("plotly.js/dist/plotly")).default as unknown as typeof import("plotly.js");
      await Plotly.downloadImage(graphDiv, { format: "png", filename, width: 1400, height: 800 });
    },
  }));

  return (
    <Plot
      data={figure.data}
      layout={{
        margin: { t: 20, r: 20, b: 40, l: 50 },
        ...figure.layout,
        autosize: true,
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "440px" }}
      useResizeHandler
      onInitialized={(_, graphDiv) => {
        graphDivRef.current = graphDiv;
      }}
      onUpdate={(_, graphDiv) => {
        graphDivRef.current = graphDiv;
      }}
    />
  );
});

export default PlotlyChart;
