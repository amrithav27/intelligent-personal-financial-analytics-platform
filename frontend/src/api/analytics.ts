import { useQuery } from '@tanstack/react-query'
import apiClient from './client'

export function useSpendingTrends(months = 6) {
  return useQuery({
    queryKey: ['analytics', 'trends', months],
    queryFn: async () => {
      const response = await apiClient.get(`/analytics/trends?months=${months}`)
      const data = response.data
      return Array.isArray(data) ? data : (data?.data || data?.trends || [])
    },
  })
}

export function useCategoryDistribution() {
  return useQuery({
    queryKey: ['analytics', 'categories'],
    queryFn: async () => {
      const response = await apiClient.get('/analytics/categories')
      const data = response.data
      return Array.isArray(data) ? data : (data?.categories || [])
    },
  })
}
