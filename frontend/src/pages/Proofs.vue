<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
const proofs = ref([])
const verify = ref(null)
onMounted(async () => {
  proofs.value = await api.proofs()
  verify.value = await api.eventTypeVerify()
})
</script>
<template>
  <div data-plant="20-allowlist-hit-audit-blank" class="plant-mark" style="display:none"></div>

  <div>
    <h1>核账</h1>
    <p class="sub">占用核对列表；邻题可扩展超时边、冲突边等证明实体。</p>

    <div class="panel" v-if="verify" style="margin-bottom:1rem">
      <h2 style="margin:0 0 .5rem; font-size:1rem">事件类型核对（只读）</h2>
      <div class="stats" style="margin-bottom:.75rem">
        <div class="stat"><b>v{{ verify.version }}</b><span>允许集版本</span></div>
        <div class="stat"><b>{{ verify.violation_count }}</b><span>在置违规</span></div>
        <div class="stat"><b>{{ verify.archived_violation_count }}</b><span>已消解留档</span></div>
        <div class="stat"><b>{{ verify.allowed_count }}</b><span>允许类型数</span></div>
      </div>
      <p class="sub">允许集：<code>{{ verify.allowed.join(', ') }}</code></p>
      <p class="sub">搁置键：<code v-if="verify.quarantine_keys.length">{{ verify.quarantine_keys.join(', ') }}</code><span v-else>无</span></p>
      <p class="sub" v-if="verify.latest_batch">
        最近批次 <code>{{ verify.latest_batch.batch_id }}</code> · v{{ verify.latest_batch.allowlist_version }}
        · 接收 {{ verify.latest_batch.accepted }} · 搁置 {{ verify.latest_batch.quarantined }}
      </p>
    </div>

    <div class="panel" style="overflow:auto">
      <table>
        <thead><tr><th>占用</th><th>格口</th><th>运单</th><th>开启</th><th>事件</th></tr></thead>
        <tbody>
          <tr v-for="p in proofs" :key="p.id">
            <td><code>{{ p.occupancy_id }}</code></td>
            <td>{{ p.cell_id }}</td>
            <td>{{ p.tracking_no }}</td>
            <td>{{ p.opened_at }}</td>
            <td><code>{{ p.event_ids_json }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
