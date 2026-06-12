import api from './client'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  reply: string
}

export const chatApi = {
  send: (message: string) =>
    api.post<ChatResponse>('/api/v1/chat/', { message }),
}
