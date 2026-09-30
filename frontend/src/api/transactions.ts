import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from './client'

export interface TransactionFilters {
  category?: string
  dateFrom?: string
  dateTo?: string
  amountMin?: number
  amountMax?: number
  search?: string
}

export function useTransactions(page = 1, pageSize = 20, filters: TransactionFilters = {}) {
  return useQuery({
    queryKey: ['transactions', page, pageSize, filters],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('page_size', String(pageSize))
      if (filters.category) params.set('category', filters.category)
      if (filters.dateFrom) params.set('date_from', filters.dateFrom)
      if (filters.dateTo) params.set('date_to', filters.dateTo)
      if (filters.amountMin != null) params.set('amount_min', String(filters.amountMin))
      if (filters.amountMax != null) params.set('amount_max', String(filters.amountMax))
      if (filters.search) params.set('search', filters.search)
      return apiClient.get(`/transactions?${params.toString()}`).then(r => r.data)
    },
    retry: 1,
  })
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => apiClient.get('/analytics/categories').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export interface ManualTransactionPayload {
  amount: number
  description: string
  merchant_name?: string
  date?: string
  currency?: string
}

export function useAddTransaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ManualTransactionPayload) =>
      apiClient.post('/transactions/manual', payload).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
    },
  })
}

export function useUploadCSV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress?: (pct: number) => void }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('source_type', 'csv_v1')
      return apiClient.post('/transactions/ingest', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
        },
      }).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
    },
  })
}
