import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from './client'

export interface Alert {
  id: string
  transaction_id: string | null
  category_id: number | null
  category_name: string | null
  category_icon: string | null
  z_score: number
  description: string
  acknowledged_at: string | null
  created_at: string
}

export interface AlertListResponse {
  alerts: Alert[]
  total: number
  page: number
  page_size: number
}

export function useAlerts(page = 1, pageSize = 20, unreadOnly = false) {
  return useQuery({
    queryKey: ['alerts', page, pageSize, unreadOnly],
    queryFn: () =>
      apiClient
        .get<AlertListResponse>('/alerts', {
          params: { page, page_size: pageSize, unread_only: unreadOnly },
        })
        .then(r => r.data),
    staleTime: 15_000,
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: string) =>
      apiClient.post(`/alerts/${alertId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
    },
  })
}
