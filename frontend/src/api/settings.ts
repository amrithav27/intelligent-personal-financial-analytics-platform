import apiClient from './client'

export interface UserProfile {
  id: string
  email: string
  display_name: string
  role: string
  created_at: string
}

export interface NotificationPref {
  category_id: number
  category_name: string
  category_icon?: string
  email_enabled: boolean
  push_enabled: boolean
  websocket_enabled: boolean
}

export const settingsAPI = {
  getProfile: () => apiClient.get<UserProfile>('/auth/me').then(res => res.data),
  
  updateProfile: (data: { display_name?: string; email?: string }) => 
    apiClient.put<UserProfile>('/auth/me', data).then(res => res.data),
    
  changePassword: (data: { current_password: string; new_password: string }) =>
    apiClient.post('/auth/me/change-password', data).then(res => res.data),
    
  getNotificationPrefs: () => 
    apiClient.get<NotificationPref[]>('/auth/me/notification-preferences').then(res => res.data),
    
  updateNotificationPrefs: (preferences: Partial<NotificationPref>[]) =>
    apiClient.put('/auth/me/notification-preferences', { preferences }).then(res => res.data),

  exportTransactions: () =>
    apiClient.get('/transactions/export', { responseType: 'blob' }).then(res => res.data)
}
