/** Minimal typings for the Plotly CDN bundle loaded in index.html. */

interface PlotlyStatic {
  react(
    el: HTMLElement,
    data: Array<Record<string, unknown>>,
    layout?: Record<string, unknown>,
    config?: Record<string, unknown>,
  ): Promise<void>;
  purge(el: HTMLElement): void;
  Plots: { resize(el: HTMLElement): void };
}

interface Window {
  Plotly: PlotlyStatic;
}
