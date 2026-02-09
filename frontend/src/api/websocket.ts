import { AgentlingEvent } from './types'

type EventHandler = (event: AgentlingEvent) => void
type ConnectionHandler = (connected: boolean) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private eventHandlers: Set<EventHandler> = new Set()
  private connectionHandlers: Set<ConnectionHandler> = new Set()
  private reconnectAttempts = 0
  private maxReconnects = 10
  private reconnectDelay = 1000
  private pingInterval: number | null = null
  private runId: string | null = null

  constructor(private baseUrl: string = `ws://${window.location.host}`) {}

  connect(runId?: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      // If already connected but switching runs, send subscribe message
      if (runId && runId !== this.runId) {
        this.ws.send(JSON.stringify({ type: 'subscribe', run_id: runId }))
        this.runId = runId
      }
      return
    }

    this.runId = runId || null
    const url = runId
      ? `${this.baseUrl}/ws/runs/${runId}`
      : `${this.baseUrl}/ws`

    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        console.log('WebSocket connected')
        this.reconnectAttempts = 0
        this.notifyConnection(true)
        this.startPing()
      }

      this.ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data)

          if (data.type === 'event' && data.data) {
            this.eventHandlers.forEach(h => h(data.data))
          } else if (data.type === 'pong') {
            // Keepalive response
          }
        } catch (e) {
          console.error('WebSocket message parse error:', e)
        }
      }

      this.ws.onclose = () => {
        console.log('WebSocket disconnected')
        this.notifyConnection(false)
        this.stopPing()
        this.attemptReconnect()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
    } catch (e) {
      console.error('WebSocket connection error:', e)
      this.attemptReconnect()
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnects) {
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts)
      console.log(`Reconnecting in ${delay}ms...`)

      setTimeout(() => {
        this.reconnectAttempts++
        this.connect(this.runId || undefined)
      }, delay)
    }
  }

  private startPing(): void {
    this.pingInterval = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }

  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private notifyConnection(connected: boolean): void {
    this.connectionHandlers.forEach(h => h(connected))
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.add(handler)
    return () => this.eventHandlers.delete(handler)
  }

  onConnection(handler: ConnectionHandler): () => void {
    this.connectionHandlers.add(handler)
    return () => this.connectionHandlers.delete(handler)
  }

  disconnect(): void {
    this.stopPing()
    this.ws?.close()
    this.ws = null
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Singleton instance
export const wsClient = new WebSocketClient()
