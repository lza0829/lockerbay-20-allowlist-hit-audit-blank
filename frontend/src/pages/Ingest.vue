<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const events = ref([])
const report = ref(null)
async function load() { events.value = await api.events() }
async function run() { report.value = await api.ingest(); await load() }
onMounted(load)
</script>
<template>
  <div data-plant="20-allowlist-hit-audit-blank" class="plant-mark" style="display:none"></div>

  <div>
    <h1>装载</h1>
    <p class="sub">投柜 / 取件事件进入主通道；基座按顺序物化占用。类型不在允许集的事件进搁置，不改占用。</p>
    <p><button @click="run">跑一批夹具</button></p>
    <pre v-if="report" class="panel">{{ report }}</pre>
    <div class="panel" v-if="report?.decisions?.length" style="margin-top:1rem; overflow:auto">
      <h2 style="margin:0 0 .5rem; font-size:1rem">本批裁决（允许集 v{{ report.allowlist_version }}）</h2>
      <table>
        <thead><tr><th>事件</th><th>类型</th><th>裁决</th><th>搁置键</th></tr></thead>
        <tbody>
          <tr v-for="d in report.decisions" :key="d.event_id">
            <td><code>{{ d.event_id }}</code></td>
            <td>{{ d.event_type }}</td>
            <td>{{ d.decision }}</td>
            <td><code>{{ d.quarantine_key || '—' }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:1rem; overflow:auto">
      <table>
        <thead><tr><th>事件</th><th>类型</th><th>格口</th><th>运单</th><th>时刻</th></tr></thead>
        <tbody>
          <tr v-for="e in events" :key="e.id">
            <td><code>{{ e.id }}</code></td>
            <td>{{ e.event_type }}</td>
            <td>{{ e.cell_id || '—' }}</td>
            <td>{{ e.tracking_no || '—' }}</td>
            <td>{{ e.event_ts }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
