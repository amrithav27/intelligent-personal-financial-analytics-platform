import { useQuery } from '@tanstack/react-query'
import apiClient from './client'

export interface DashboardOverview {
  fhs: { score: number; computed_at: string; data_freshness: 'fresh' | 'stale' }
  categories: Array<{ category: string; amount: number; count: number }>
  recent_transactions: Array<{
    id: string; amount: number; currency: string;
    merchant_name: string; description: string; ts: string; category: string
  }>
  unread_alerts: number
  budget_status: Array<{ category: string; limit: number; spent: number; status: 'ok'|'warning'|'over' }>
}

export function useDashboardOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: () => apiClient.get<DashboardOverview>('/dashboard/overview').then(r => r.data),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
}

export function useFHSHistory(months = 6) {
  return useQuery({
    queryKey: ['analytics', 'fhs', 'history', months],
    queryFn: async () => {
      const response = await apiClient.get(`/analytics/fhs/history?months=${months}`)
      const data = response.data

      // Try common shapes and normalize to an array of { computed_at, score }
      let arr: any[] = []
      if (Array.isArray(data)) arr = data
      else if (Array.isArray(data?.history)) arr = data.history
      else if (Array.isArray(data?.results)) arr = data.results
      else if (Array.isArray(data?.data)) arr = data.data
      else if (data && typeof data === 'object') {
        // If object contains items under other keys
        arr = data.items || data.history || data.results || []
      }

      // Normalize each entry to ensure computed_at and score exist
      const normalized = arr.map((d: any) => {
        const computed_at = d.computed_at || d.ts || d.date || d.created_at || null
        const score = (d.score ?? d.fhs ?? d.value ?? null)
        return { computed_at, score }
      }).filter((d: any) => d.computed_at && typeof d.score === 'number')

      return normalized
    },
  })
}
