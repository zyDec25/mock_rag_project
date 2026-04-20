import { AxiosRequestConfig } from 'axios'
import { request } from './request'

export function register(
  params: {
    username: string
    password: string
  },
  options?: AxiosRequestConfig,
) {
  return request.post<{
    message: string
    user: {
      id: number
      username: string
    }
  }>(`/auth/register`, params, options)
}

export function login(
  params: {
    username: string
    password: string
  },
  options?: AxiosRequestConfig,
) {
  return request.post<{
    message: string
    access_token: string
    token_type: string
    user: {
      id: number
      username: string
    }
  }>(`/auth/login`, params, options)
}

export function me(options?: AxiosRequestConfig) {
  return request.get<{
    id: number
    username: string
  }>(`/auth/me`, options)
}
