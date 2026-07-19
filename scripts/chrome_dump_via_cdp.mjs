#!/usr/bin/env node

import { spawn } from 'node:child_process'


function argument(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : fallback
}

const chrome = argument('--chrome')
const userDataDir = argument('--user-data-dir')
const profileDirectory = argument('--profile-directory', 'Default')
const targetUrl = argument('--url')
const primeUrls = process.argv
  .flatMap((value, index) => value === '--prime-url' ? [process.argv[index + 1]] : [])
  .filter(Boolean)
const port = Number(argument('--port', String(19000 + Math.floor(Math.random() * 500))))

if (!chrome || !userDataDir || !targetUrl || !Number.isInteger(port)) {
  throw new Error('required: --chrome --user-data-dir --url [--prime-url URL]')
}

const browser = spawn(
  chrome,
  [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--disable-background-networking',
    `--remote-debugging-port=${port}`,
    '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${userDataDir}`,
    `--profile-directory=${profileDirectory}`,
    'about:blank',
  ],
  { stdio: ['ignore', 'ignore', 'pipe'] },
)

let browserError = ''
browser.stderr.on('data', (chunk) => {
  browserError = `${browserError}${chunk.toString('utf8')}`.slice(-4000)
})

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

async function pageTarget() {
  let lastError
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`)
      const targets = await response.json()
      const page = targets.find((item) => item.type === 'page')
      if (page?.webSocketDebuggerUrl) return page
    } catch (error) {
      lastError = error
    }
    if (browser.exitCode !== null) {
      throw new Error(`Chrome exited rc=${browser.exitCode}: ${browserError}`)
    }
    await sleep(250)
  }
  throw new Error(`Chrome CDP endpoint unavailable: ${lastError || browserError}`)
}

async function main() {
  const target = await pageTarget()
  const socket = new WebSocket(target.webSocketDebuggerUrl)
  let nextId = 1
  const pending = new Map()
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (!message.id || !pending.has(message.id)) return
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(JSON.stringify(message.error)))
    else resolve(message.result)
  }
  await new Promise((resolve, reject) => {
    socket.onopen = resolve
    socket.onerror = () => reject(new Error('Chrome CDP WebSocket connection failed'))
  })
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId
    nextId += 1
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method, params }))
  })
  await send('Page.enable')
  let referrer = ''
  for (const url of [...primeUrls, targetUrl]) {
    await send('Page.navigate', referrer ? { url, referrer } : { url })
    await sleep(1800)
    referrer = url
  }
  const evaluated = await send('Runtime.evaluate', {
    expression: 'document.documentElement.outerHTML',
    returnByValue: true,
  })
  const html = evaluated?.result?.value
  if (typeof html !== 'string' || !html.trim()) {
    throw new Error('Chrome CDP returned an empty DOM')
  }
  process.stdout.write(html)
  try {
    await send('Browser.close')
  } catch {
    browser.kill()
  }
  socket.close()
}

const timeout = setTimeout(() => {
  browser.kill()
  process.stderr.write(`Chrome CDP dump timed out: ${browserError}\n`)
  process.exit(2)
}, 60000)

try {
  await main()
  clearTimeout(timeout)
} catch (error) {
  clearTimeout(timeout)
  browser.kill()
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n${browserError}`)
  process.exit(1)
}
