import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision'

export type HandLandmarkerLike = Pick<HandLandmarker, 'detectForVideo' | 'close'>

const VISION_VERSION = '1.2.3'
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VISION_VERSION}/wasm`
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'

export async function createHandLandmarker(): Promise<HandLandmarkerLike> {
  const vision = await FilesetResolver.forVisionTasks(WASM_URL)
  const options = {
    baseOptions: { modelAssetPath: MODEL_URL },
    runningMode: 'VIDEO' as const,
    numHands: 2,
    minHandDetectionConfidence: 0.55,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  }
  try {
    return await HandLandmarker.createFromOptions(vision, { ...options, baseOptions: { ...options.baseOptions, delegate: 'GPU' } })
  } catch {
    // CPU fallback for devices/browsers without a compatible GPU delegate.
    return HandLandmarker.createFromOptions(vision, options)
  }
}
