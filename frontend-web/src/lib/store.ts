import { create } from "zustand";
import type { StatTestResult, StatsHistoryEntry } from "./types";

type AppState = {
  pdfUploaded: boolean;
  pdfFilename: string;
  setPdfUploaded: (filename: string) => void;
  removePdf: () => void;

  csvSessionId: string | null;
  csvFilename: string;
  csvColumns: string[];
  csvDtypes: Record<string, string>;
  csvPreview: Record<string, string>[];
  csvRows: number;
  setCsvSession: (data: {
    sessionId: string;
    filename: string;
    columns: string[];
    dtypes: Record<string, string>;
    preview: Record<string, string>[];
    rows: number;
  }) => void;
  removeCsvSession: () => void;

  lastStatsResult: StatTestResult | null;
  setLastStatsResult: (result: StatTestResult | null) => void;
  statsHistory: StatsHistoryEntry[];
  addStatsHistory: (entry: StatsHistoryEntry) => void;
  clearStatsHistory: () => void;
};

export const useAppStore = create<AppState>((set) => ({
  pdfUploaded: false,
  pdfFilename: "",
  setPdfUploaded: (filename) => set({ pdfUploaded: true, pdfFilename: filename }),
  removePdf: () => set({ pdfUploaded: false, pdfFilename: "" }),

  csvSessionId: null,
  csvFilename: "",
  csvColumns: [],
  csvDtypes: {},
  csvPreview: [],
  csvRows: 0,
  setCsvSession: ({ sessionId, filename, columns, dtypes, preview, rows }) =>
    set({
      csvSessionId: sessionId,
      csvFilename: filename,
      csvColumns: columns,
      csvDtypes: dtypes,
      csvPreview: preview,
      csvRows: rows,
    }),
  removeCsvSession: () =>
    set({
      csvSessionId: null,
      csvFilename: "",
      csvColumns: [],
      csvDtypes: {},
      csvPreview: [],
      csvRows: 0,
    }),

  lastStatsResult: null,
  setLastStatsResult: (result) => set({ lastStatsResult: result }),
  statsHistory: [],
  addStatsHistory: (entry) => set((s) => ({ statsHistory: [...s.statsHistory, entry] })),
  clearStatsHistory: () => set({ statsHistory: [] }),
}));
