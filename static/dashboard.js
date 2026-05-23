const COLORS = ['#e8b84b','#388bfd','#3dd68c','#f75f67','#39d0d8'];

const _raw = window.dashboardData || [];
const initData = {
  fullLabels: _raw.map(c => c.name),
  labels:     _raw.map(c => c.name.split(' ').slice(-1)[0]),
  emojis:     _raw.map(c => c.emoji),
  votes:      _raw.map(c => c.vote_count),
};
const ctx = document.getElementById('barChart').getContext('2d');
const barChart = new Chart(ctx, {
  type: 'bar',
  data: {
    labels: initData.labels.map((l, i) => initData.emojis[i] + ' ' + l),
    datasets: [{
      label: 'Votes',
      data: initData.votes,
      backgroundColor: COLORS.map(c => c + '33'),
      borderColor: COLORS,
      borderWidth: 2,
      borderRadius: 8,
      borderSkipped: false,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 800 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(13,24,42,0.95)',
        borderColor: 'rgba(56,139,253,0.25)',
        borderWidth: 1,
        titleColor: '#fff',
        bodyColor: '#cdd9e5',
        padding: 12,
        callbacks: {
          title: (items) => initData.fullLabels[items[0].dataIndex],
          label: (item) => {
            const total = item.dataset.data.reduce((a, b) => a + b, 0);
            const pct = total > 0 ? Math.round(item.raw / total * 100) : 0;
            return ` ${item.raw} votes (${pct}%)`;
          }
        }
      }
    },
    scales: {
      x: { grid:{color:'rgba(255,255,255,0.04)'}, ticks:{color:'#8b949e'}, border:{color:'rgba(255,255,255,0.06)'} },
      y: { beginAtZero:true, grid:{color:'rgba(255,255,255,0.04)'}, ticks:{color:'#8b949e',stepSize:1,callback:v=>Number.isInteger(v)?v:''}, border:{color:'rgba(255,255,255,0.06)'} }
    }
  }
});

function buildList(candidates, total) {
  if (!candidates.length) return '<div style="text-align:center;padding:2rem;color:#4a5568">No votes yet</div>';
  return candidates.map((c, i) => {
    const pct = total > 0 ? Math.round(c.vote_count / total * 100) : 0;
    const win = i === 0 && c.vote_count > 0;
    return `<div class="result-row ${win?'winner':''}">
      <div class="rr-rank ${win?'gold':''}">${win?'👑':'#'+(i+1)}</div>
      <div class="rr-emoji">${c.emoji}</div>
      <div class="rr-info">
        <div class="rr-name">${c.name}</div>
        <div class="rr-party">${c.party}</div>
        <div class="prog-bar"><div class="prog-fill" style="width:${pct}%"></div></div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div class="rr-count">${c.vote_count}</div>
        <div class="rr-pct">${pct}%</div>
      </div>
    </div>`;
  }).join('');
}

function refreshData() {
  fetch('/api/results')
    .then(r => r.json())
    .then(data => {
      const cands = data.candidates;
      const total = data.total;
      document.getElementById('votedCount').textContent  = data.voted_count;
      document.getElementById('turnoutPct').textContent  = data.turnout + '%';
      document.getElementById('totalLabel').textContent  = total + ' votes total';
      document.getElementById('standingsSub').textContent = total + ' total votes';
      barChart.data.datasets[0].data = initData.fullLabels.map(name => {
        const found = cands.find(c => c.name === name);
        return found ? found.vote_count : 0;
      });
      barChart.update('active');
      document.getElementById('resultsList').innerHTML = buildList(cands, total);
    }).catch(()=>{});
}
setInterval(refreshData, 5000);
