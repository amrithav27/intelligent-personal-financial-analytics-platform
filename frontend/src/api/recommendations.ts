import { useQuery } from '@tanstack/react-query'
import apiClient from './client'

export function useBudgetRecommendations(month?: string) {
  return useQuery({
    queryKey: ['recommendations', 'budget', month],
    queryFn: () => apiClient.get(`/recommendations/budget${month ? `?month=${month}` : ''}`).then(r => r.data),
  })
}
