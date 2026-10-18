import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { UpdateConfigRequest } from '@/types/api'

/**
 * @description React Query Hooks
 * @responsibility 封装数据查询和变更的自定义 Hooks
 */

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: async () => {
      const response = await api.get('/api/status')
      return response.data.data
    },
    refetchInterval: 30000,
  })
}

export function useTasks(page = 1, pageSize = 100) {
  return useQuery({
    queryKey: ['tasks', page, pageSize],
    queryFn: async () => {
      const params = { page, page_size: pageSize }
      const response = await api.get('/api/tasks', { params })
      return response.data.data
    },
    placeholderData: (previousData) => previousData,
  })
}

export function useAddTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: { magnet: string; library_name: string; name?: string }) => {
      const response = await api.post('/api/tasks', data)
      return response.data.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (taskId: string) => {
      const response = await api.delete(`/api/tasks/${taskId}`)
      return response.data.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export function useLibraries() {
  return useQuery({
    queryKey: ['libraries'],
    queryFn: async () => {
      const response = await api.get('/api/libraries')
      return response.data.data.libraries
    },
  })
}

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: async () => {
      const response = await api.get('/api/config')
      return response.data.data
    },
  })
}

export function useUpdateConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: UpdateConfigRequest) => {
      const response = await api.put('/api/config', data)
      return response.data.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })
}

export function useOrganizeRecords(page = 1, pageSize = 10, status?: string) {
  return useQuery({
    queryKey: ['organize-records', page, pageSize, status],
    queryFn: async () => {
      const params = { page, page_size: pageSize, status }
      const response = await api.get('/api/organize/records', { params })
      return response.data.data
    },
    placeholderData: (previousData) => previousData,
  })
}
