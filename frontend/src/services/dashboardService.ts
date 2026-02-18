import { api } from '@/services/api';

/**
 * Dashboard KPI & Chart service.
 *
 * Consumes the S6-3 "Controlled BI Semantic Facade" endpoints:
 *   - GET /dashboards/kpi/summary
 *   - GET /dashboards/charts/sales-trend
 */

// ---------- Types ----------

export interface KpiCard {
  label: string;
  value: number;
  currency: string;
}

export interface KpiSummaryResponse {
  success: boolean;
  data: {
    tenant_id: string;
    generated_at: string;
    cards: KpiCard[];
    currency: string;
  };
  timestamp: string;
}

export interface ChartDataPoint {
  date: string;
  value: number;
  currency: string;
}

export interface ChartDataResponse {
  success: boolean;
  data: {
    tenant_id: string;
    chart_type: string;
    granularity: string;
    data: ChartDataPoint[];
    currency: string;
  };
  timestamp: string;
}

// ---------- Service ----------

export const dashboardService = {
  /**
   * Fetch KPI summary cards (backend-hardcoded metrics).
   * Gracefully degrades if materialized views are empty.
   */
  getKpiSummary: () =>
    api.get<KpiSummaryResponse>('/dashboards/kpi/summary'),

  /**
   * Fetch sales trend chart (last N days).
   * Metric is hardcoded to REVENUE — only date range is configurable.
   */
  getSalesTrend: (dateFrom?: string, dateTo?: string, granularity = 'day') =>
    api.get<ChartDataResponse>('/dashboards/charts/sales-trend', {
      params: {
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
        granularity,
      },
    }),
};
