(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var success = style.getPropertyValue('--success').trim();
  var warning = style.getPropertyValue('--warning').trim();
  var danger = style.getPropertyValue('--danger').trim();

  // --- Chart: Service Trend ---
  var chart1 = echarts.init(document.getElementById('chart-service-trend'), null, { renderer: 'svg' });
  var hours = Array.from({length: 24}, (_, i) => i + ':00');
  var todayData = [12,8,5,3,2,4,15,45,120,280,420,580,650,620,580,540,480,420,350,280,180,120,80,45];
  var yesterdayData = [10,7,4,3,3,5,18,50,110,260,400,550,600,580,540,500,450,400,330,260,170,110,70,40];
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink }
    },
    legend: {
      data: ['今日', '昨日'],
      textStyle: { color: muted },
      top: 0
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '40', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: hours,
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted }
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule, opacity: 0.3 } }
    },
    series: [
      {
        name: '今日',
        type: 'line',
        smooth: true,
        data: todayData,
        lineStyle: { color: accent, width: 3 },
        itemStyle: { color: accent },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: accent + '40' },
              { offset: 1, color: accent + '05' }
            ]
          }
        }
      },
      {
        name: '昨日',
        type: 'line',
        smooth: true,
        data: yesterdayData,
        lineStyle: { color: muted, width: 2, type: 'dashed' },
        itemStyle: { color: muted }
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart: Sentiment Distribution ---
  var chart2 = echarts.init(document.getElementById('chart-sentiment'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink },
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center',
      textStyle: { color: muted }
    },
    series: [
      {
        name: '情感分布',
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: bg2,
          borderWidth: 2
        },
        label: {
          show: true,
          color: ink,
          formatter: '{b}\n{d}%'
        },
        data: [
          { value: 68, name: '正面', itemStyle: { color: success } },
          { value: 22, name: '中性', itemStyle: { color: warning } },
          { value: 10, name: '负面', itemStyle: { color: danger } }
        ]
      }
    ]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart: QA Type Radar ---
  var chart3 = echarts.init(document.getElementById('chart-qa-radar'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink }
    },
    legend: {
      data: ['本周', '上周'],
      textStyle: { color: muted },
      top: 0
    },
    radar: {
      indicator: [
        { name: '历史文化', max: 100 },
        { name: '交通指引', max: 100 },
        { name: '餐饮推荐', max: 100 },
        { name: '门票信息', max: 100 },
        { name: '景点介绍', max: 100 },
        { name: '周边服务', max: 100 },
        { name: '其他咨询', max: 100 }
      ],
      shape: 'polygon',
      splitNumber: 4,
      axisName: { color: muted },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '问答类型分布',
        type: 'radar',
        data: [
          {
            value: [85, 62, 45, 78, 92, 38, 25],
            name: '本周',
            lineStyle: { color: accent, width: 2 },
            itemStyle: { color: accent },
            areaStyle: { color: accent + '30' }
          },
          {
            value: [72, 55, 50, 70, 85, 42, 30],
            name: '上周',
            lineStyle: { color: muted, width: 2, type: 'dashed' },
            itemStyle: { color: muted },
            areaStyle: { color: muted + '15' }
          }
        ]
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
