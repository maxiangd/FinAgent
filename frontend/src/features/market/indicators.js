// 常用技术指标计算（均线 / MACD / KDJ / RSI）
// 输入为聚合后的 OHLC 序列；输出与输入等长的数组，前段无数据处以 null 占位

// 简单移动平均，前 n-1 位为 null
export function calcMA(closes, n) {
  const out = new Array(closes.length).fill(null)
  let sum = 0
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i]
    if (i >= n) sum -= closes[i - n]
    if (i >= n - 1) out[i] = +(sum / n).toFixed(2)
  }
  return out
}

// 指数移动平均
function calcEMA(src, n) {
  const out = new Array(src.length).fill(null)
  if (!src.length) return out
  const k = 2 / (n + 1)
  let prev = src[0]
  out[0] = prev
  for (let i = 1; i < src.length; i++) {
    prev = src[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

// MACD(12, 26, 9)：dif / dea / hist（hist = 2 * (dif - dea)）
export function calcMACD(closes, { short = 12, long = 26, signal = 9 } = {}) {
  const emaShort = calcEMA(closes, short)
  const emaLong = calcEMA(closes, long)
  const dif = closes.map((_, i) => (i === 0 ? 0 : +(emaShort[i] - emaLong[i]).toFixed(3)))
  const dea = calcEMA(dif, signal).map((v) => (v == null ? null : +v.toFixed(3)))
  const hist = closes.map((_, i) =>
    dea[i] == null ? null : +((dif[i] - dea[i]) * 2).toFixed(3)
  )
  return { dif, dea, hist }
}

// KDJ(9, 3, 3)：国内常见 SMA 平滑算法
export function calcKDJ(kline, { n = 9, m1 = 3, m2 = 3 } = {}) {
  const k = new Array(kline.length).fill(null)
  const d = new Array(kline.length).fill(null)
  const j = new Array(kline.length).fill(null)
  let prevK = 50
  let prevD = 50
  for (let i = 0; i < kline.length; i++) {
    if (i < n - 1) {
      k[i] = 50
      d[i] = 50
      j[i] = 50
      prevK = 50
      prevD = 50
      continue
    }
    const window = kline.slice(i - n + 1, i + 1)
    const high = Math.max(...window.map((x) => x.high))
    const low = Math.min(...window.map((x) => x.low))
    const close = kline[i].close
    const rsv = high === low ? 50 : ((close - low) / (high - low)) * 100
    prevK = (prevK * (m1 - 1) + rsv) / m1
    prevD = (prevD * (m2 - 1) + prevK) / m2
    const kJ = 3 * prevK - 2 * prevD
    k[i] = +prevK.toFixed(1)
    d[i] = +prevD.toFixed(1)
    j[i] = +kJ.toFixed(1)
  }
  return { k, d, j }
}

// RSI（Wilder 平滑，输出 0-100）
export function calcRSI(closes, periods = [6, 12, 24]) {
  const result = {}
  for (const n of periods) {
    const out = new Array(closes.length).fill(null)
    let avgGain = 0
    let avgLoss = 0
    for (let i = 1; i < closes.length; i++) {
      const diff = closes[i] - closes[i - 1]
      const gain = Math.max(diff, 0)
      const loss = Math.max(-diff, 0)
      if (i <= n) {
        avgGain += gain
        avgLoss += loss
        if (i === n) {
          avgGain /= n
          avgLoss /= n
          out[i] = rsiVal(avgGain, avgLoss)
        }
      } else {
        avgGain = (avgGain * (n - 1) + gain) / n
        avgLoss = (avgLoss * (n - 1) + loss) / n
        out[i] = rsiVal(avgGain, avgLoss)
      }
    }
    result[`rsi${n}`] = out.map((v) => (v == null ? null : +v.toFixed(1)))
  }
  return result
}

function rsiVal(avgGain, avgLoss) {
  if (avgLoss === 0) return 100
  const rs = avgGain / avgLoss
  return 100 - 100 / (1 + rs)
}