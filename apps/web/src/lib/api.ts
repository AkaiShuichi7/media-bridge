/**
 * @description API 客户端
 * @responsibility 统一的 axios 实例与响应错误拦截
 */
import axios from 'axios'

// 重要：使用相对路径，通过 Vite 代理到后端，避免 CORS 错误
// 代理配置在 vite.config.ts 中：/api -> http://localhost:8000
export const api = axios.create({
  baseURL: '',  // 使用相对路径，通过 Vite 代理
  headers: {
    'Content-Type': 'application/json',
  },
})

// 响应拦截器：错误原样透传，由 react-query 层统一处理
api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
)
