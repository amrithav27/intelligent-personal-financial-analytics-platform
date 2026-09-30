import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from './client'

export interface BudgetRecommendation {
    category_id: number
    category_name: string
    recommended_amount: number
    current_limit: number | null      // user-saved override (null if not set)
    effective_limit: number           // current_limit ?? recommended_amount
    current_spending: number          // actual spend this month
    pct_used: number                  // 0–100+ percentage
    alert_level: 'ok' | 'warning' | 'over'
    strategy: string
    bucket?: string                   // needs / wants / savings (50/30/20 only)
    median_spending?: number          // statistical strategy only
}

export interface BudgetResponse {
    month: string
    strategy_used: string
    months_of_history: number
    current_month_income: number
    recommendations: BudgetRecommendation[]
}

export function useBudgets(month?: string) {
    const params = month ? `?month=${month}` : ''
    return useQuery<BudgetResponse>({
        queryKey: ['budgets', month ?? 'current'],
        queryFn: () => apiClient.get(`/recommendations/budget${params}`).then(r => r.data),
        staleTime: 30_000,
    })
}

export function useOverrideBudget() {
    const qc = useQueryClient()
    return useMutation({
        mutationFn: ({ categoryId, limitAmount, month }: {
            categoryId: number
            limitAmount: number
            month: string
        }) => {
            const params = new URLSearchParams({
                limit_amount: String(limitAmount),
                month,
            })
            return apiClient
                .post(`/recommendations/budget/${categoryId}/override?${params}`)
                .then(r => r.data)
        },
        onSuccess: (_data, vars) => {
            qc.invalidateQueries({ queryKey: ['budgets', vars.month] })
            qc.invalidateQueries({ queryKey: ['budgets', 'current'] })
            qc.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
        },
    })
}
