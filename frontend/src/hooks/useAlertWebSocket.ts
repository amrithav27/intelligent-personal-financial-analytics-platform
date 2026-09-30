import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'

export function useAlertWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const queryClient = useQueryClient()
  const token = useAuthStore(s => s.accessToken)

  useEffect(() => {
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/v1/alerts?token=${token}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      const alert = JSON.parse(event.data)
      if (alert.type === 'alert') {
        // Invalidate both dashboard and alerts caches
        queryClient.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
        queryClient.invalidateQueries({ queryKey: ['alerts'] })

        // Dispatch custom event for toast notification
        window.dispatchEvent(new CustomEvent('phoenix:alert', { detail: alert }))
      }
    }

    // Keepalive ping every 30s
    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30_000)

    return () => {
      clearInterval(pingInterval)
      ws.close()
    }
  }, [token, queryClient])
}
