<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const hours = ref(48)
const msg = ref('')
const allowed = ref([])
const saved = ref([])
const candidates = ref([])
const required = ref([])
const version = ref(null)
const typeMsg = ref('')
const custom = ref('')

function hydrate(data) {
  version.value = data.version
  allowed.value = [...data.allowed]
  saved.value = [...data.allowed]
  candidates.value = data.candidate_types || []
  required.value = data.required_types || []
}

onMounted(async () => {
  const s = await api.settings()
  hours.value = s.overdue_hours
  hydrate(s.event_type_allowlist)
})

async function save() {
  const r = await api.setOverdue(Number(hours.value))
  hours.value = r.overdue_hours
  msg.value = '已保存'
}

function toggle(t) {
  if (required.value.includes(t)) return
  const i = allowed.value.indexOf(t)
  if (i >= 0) allowed.value.splice(i, 1)
  else allowed.value.push(t)
}

async function saveTypes() {
  typeMsg.value = ''
  try {
    const r = await api.setEventTypes([...allowed.value].sort())
    version.value = r.version
    saved.value = [...r.allowed]
    allowed.value = [...r.allowed]
    typeMsg.value = r.changed ? `已保存为 v${r.version}` : `集合未变化（仍为 v${r.version}）`
  } catch (err) {
    typeMsg.value = String(err.message || err)
  }
}

function addCustom() {
  const value = custom.value.trim()
  if (!value) return
  if (!allowed.value.includes(value)) allowed.value.push(value)
  custom.value = ''
}
</script>
<template>
  <div data-plant="20-allowlist-hit-audit-blank" class="plant-mark" style="display:none"></div>

  <div>
    <h1>柜规</h1>
    <p class="sub">超时回收小时数（供后续空桩裁决；基座先可配置落库）。</p>
    <div class="panel" style="max-width:420px; display:flex; gap:.75rem; align-items:center">
      <label>overdue_hours
        <input v-model.number="hours" type="number" min="1" style="margin-left:.5rem; width:5rem; background:#111827; color:#e8eef6; border:1px solid #334155; border-radius:4px; padding:.3rem" />
      </label>
      <button @click="save">保存</button>
      <span class="sub">{{ msg }}</span>
    </div>

    <div class="panel" style="margin-top:1rem; max-width:640px">
      <h2 style="margin:0 0 .35rem; font-size:1rem">包裹事件类型允许集 <small class="sub">当前 v{{ version }}</small></h2>
      <p class="sub">集合外的事件装载时进搁置，不改占用与格口；已物化的历史占用不受版本刷新影响。</p>
      <div style="display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:.75rem">
        <button
          v-for="t in [...new Set([...candidates, ...allowed])]"
          :key="t"
          :class="{ on: allowed.includes(t), locked: required.includes(t) }"
          :disabled="required.includes(t)"
          :title="required.includes(t) ? '必需类型，不可移除' : ''"
          @click="toggle(t)"
        >{{ allowed.includes(t) ? '✓ ' : '' }}{{ t }}</button>
      </div>
      <div style="display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem">
        <input v-model="custom" placeholder="自定义 event_type" style="background:#111827; color:#e8eef6; border:1px solid #334155; border-radius:4px; padding:.3rem .5rem" @keyup.enter="addCustom" />
        <button @click="addCustom">加入</button>
      </div>
      <button @click="saveTypes" :disabled="JSON.stringify([...allowed].sort()) === JSON.stringify(saved)">保存允许集</button>
      <span class="sub" style="margin-left:.75rem">{{ typeMsg }}</span>
    </div>
  </div>
</template>
