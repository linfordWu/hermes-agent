import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { type MicRecorderErrorCopy, useMicRecorder } from './use-mic-recorder'

// The level meter behind continuous voice mode is an AudioContext on the
// capture stream. #75329: a torn-down context was still closing when the next
// take opened another, the device errored, and the dead meter silently
// dropped every later utterance.

const copy: MicRecorderErrorCopy = {
  microphoneAccessDenied: 'denied',
  microphoneConstraintsUnsupported: 'constraints',
  microphoneInUse: 'in use',
  microphoneNeedsHttps: 'needs https',
  microphonePermissionDenied: 'permission',
  microphoneStartFailed: 'start failed',
  microphoneUnsupported: 'unsupported',
  noMicrophone: 'no mic'
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(done => (resolve = done))

  return { promise, resolve }
}

class FakeAudioContext extends EventTarget {
  static instances: FakeAudioContext[] = []
  static throwOnConstruct = false
  static closeCalls = 0
  state: AudioContextState = 'running'
  closing = deferred()

  constructor() {
    super()

    if (FakeAudioContext.throwOnConstruct) {
      throw new DOMException('too many contexts', 'NotSupportedError')
    }

    FakeAudioContext.instances.push(this)
  }

  createAnalyser() {
    return { fftSize: 0, getByteTimeDomainData: (data: Uint8Array) => data.fill(128) }
  }

  createMediaStreamSource() {
    return { connect: vi.fn(), disconnect: vi.fn() }
  }

  resume = vi.fn(async () => {
    this.state = 'running'
  })

  suspend = vi.fn(async () => {
    this.state = 'suspended'
  })

  close() {
    FakeAudioContext.closeCalls += 1

    return this.closing.promise.then(() => {
      this.state = 'closed'
      this.dispatchEvent(new Event('statechange'))
    })
  }
}

class FakeMediaRecorder {
  static isTypeSupported = () => true
  mimeType = 'audio/webm'
  state: RecordingState = 'inactive'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: ((event: Event) => void) | null = null

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['clip'], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}

const flush = () => act(async () => new Promise<void>(resolve => window.setTimeout(resolve, 0)))

beforeEach(() => {
  FakeAudioContext.instances = []
  FakeAudioContext.throwOnConstruct = false
  FakeAudioContext.closeCalls = 0
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn(() => 1)
  )
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) }
  })
})

afterEach(() => {
  cleanup()
  FakeAudioContext.instances.forEach(context => context.closing.resolve())
  vi.unstubAllGlobals()
})

describe('useMicRecorder level meter', () => {
  it('reuses the meter context across takes and suspends it between recordings', async () => {
    const { result } = renderHook(() => useMicRecorder(copy))

    await act(async () => {
      await result.current.handle.start()
    })
    await act(async () => {
      await result.current.handle.stop()
    })

    const context = FakeAudioContext.instances[0]
    await flush()

    expect(context.suspend).toHaveBeenCalledOnce()
    expect(FakeAudioContext.closeCalls).toBe(0)

    await act(async () => {
      await result.current.handle.start()
    })
    await flush()

    expect(FakeAudioContext.instances).toHaveLength(1)
    expect(context.resume).toHaveBeenCalledTimes(2)
    await act(async () => {
      await result.current.handle.stop()
    })
    expect(context.suspend).toHaveBeenCalledTimes(2)
  })

  it('closes the reused meter context when the hook unmounts', async () => {
    const { result, unmount } = renderHook(() => useMicRecorder(copy))

    await act(async () => {
      await result.current.handle.start()
      await result.current.handle.stop()
    })

    unmount()

    expect(FakeAudioContext.closeCalls).toBe(1)
  })

  it('reports a device error on the meter and marks the take meterFailed', async () => {
    const onMeterFailure = vi.fn()
    const { result } = renderHook(() => useMicRecorder(copy))

    await act(async () => {
      await result.current.handle.start({ onMeterFailure, onSilence: vi.fn(), silenceLevel: 0.075, silenceMs: 1_250 })
    })

    FakeAudioContext.instances[0].dispatchEvent(new Event('error'))
    await flush()

    expect(onMeterFailure).toHaveBeenCalledOnce()

    let recording: Awaited<ReturnType<typeof result.current.handle.stop>> = null

    await act(async () => {
      recording = await result.current.handle.stop()
    })

    expect(recording).toMatchObject({ heardSpeech: false, meterFailed: true })
  })

  it('treats a meter that cannot be built as failed instead of silently deaf', async () => {
    FakeAudioContext.throwOnConstruct = true
    const onMeterFailure = vi.fn()
    const { result } = renderHook(() => useMicRecorder(copy))

    await act(async () => {
      await result.current.handle.start({ onMeterFailure })
    })
    await flush()

    expect(onMeterFailure).toHaveBeenCalledOnce()
  })

  it('does not report suspending the meter after a take as a failure', async () => {
    const onMeterFailure = vi.fn()
    const { result } = renderHook(() => useMicRecorder(copy))

    await act(async () => {
      await result.current.handle.start({ onMeterFailure })
    })

    let recording: Awaited<ReturnType<typeof result.current.handle.stop>> = null

    await act(async () => {
      recording = await result.current.handle.stop()
    })
    await flush()

    expect(onMeterFailure).not.toHaveBeenCalled()
    expect(recording).toMatchObject({ meterFailed: false })
  })
})
