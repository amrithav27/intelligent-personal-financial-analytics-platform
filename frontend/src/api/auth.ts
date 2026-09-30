import apiClient from './client'

export const authAPI = {
  register: (data: { email: string; display_name: string; password: string }) =>
    apiClient.post('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    apiClient.post('/auth/login', data),
  refresh: (refreshToken: string) =>
    apiClient.post('/auth/refresh', { refresh_token: refreshToken }),
}
