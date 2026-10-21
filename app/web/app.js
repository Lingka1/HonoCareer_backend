'use strict';
const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid=()=>crypto.randomUUID();
const sceneNames={employment:'求职面试',volunteer:'志愿者面试',club:'社团面试'};
const stages=['opening','self_introduction','experience_followup','situational_questions','candidate_questions','review'];
const stageNames=['开场','自我介绍','经历追问','情景提问','反问','复盘'];
const statusNames={active:'进行中',generating_report:'报告生成中',completed:'已完成',failed:'生成失败',cancelled:'已取消'};
const dimensionNames={expression_clarity:'表达清晰度',logic:'逻辑性',role_match:'岗位/场景匹配度',adaptability:'应变能力'};
const readStore=(key,fallback)=>{try{return JSON.parse(sessionStorage.getItem(key))??fallback}catch{return fallback}};
const state={tokens:readStore('hc-tokens',null),user:readStore('hc-user',null),page:'home',scene:'employment',profiles:[],resumes:[],sessions:[],session:null,messages:[],report:null,weak:[],memories:[],enabled:true,offline:false,busy:false,newProfile:false,historyFilter:'all',historyCursor:null,health:null,authMode:'login',stream:null,reportTimer:null,epoch:0};
const cacheKey=name=>'hc-cache:'+state.user?.userId+':'+name;
function cache(name,value){if(!state.user)return;try{localStorage.setItem(cacheKey(name),JSON.stringify(value))}catch{}}
function syncSession(session){if(!session)return;const index=state.sessions.findIndex(s=>s.sessionId===session.sessionId);if(index<0)state.sessions.unshift(session);else state.sessions[index]={...state.sessions[index],...session};state.sessions.sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));cache('sessions',state.sessions);$('#history-count').textContent=state.sessions.length}
function cached(name,fallback){try{return JSON.parse(localStorage.getItem(cacheKey(name)))??fallback}catch{return fallback}}
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('visible'),4500)}
function date(value){return value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):''}
function storeAuth(tokens,user){state.tokens=tokens;if(user)state.user=user;sessionStorage.setItem('hc-tokens',JSON.stringify(tokens));sessionStorage.setItem('hc-user',JSON.stringify(state.user));updateAccount()}
function updateAccount(){$('#account-name').textContent=state.user?.nickname||'登录后开始练习';$('#avatar').textContent=(state.user?.nickname||'同').slice(0,1)}
function badge(){const data=state.health;const el=$('#mode-badge');el.className='status-badge'+(state.offline?' offline':data?.provider==='demo'?' demo':'');el.textContent=state.offline?'离线 · 查看本地缓存':data?.provider==='demo'?'本地规则演示':data?.llmConfigured?'DeepSeek 云端已配置':'云端模型待配置'}
async function api(path,options={},retry=true){
  const epoch=state.epoch;
  const headers={...(options.headers||{})};
  if(state.tokens)headers.Authorization='Bearer '+state.tokens.accessToken;
  if(options.body && !(options.body instanceof FormData))headers['Content-Type']='application/json';
  let response;
  try{response=await fetch('/api/v1'+path,{...options,headers,body:options.body?(options.body instanceof FormData?options.body:JSON.stringify(options.body)):undefined})}catch{state.offline=true;badge();throw new Error('网络不可用，已保留本地记录。请恢复连接后重试。')}
  const data=await response.json();
  if(epoch!==state.epoch)throw new Error('账号状态已切换，请重新操作');
  if(response.status===401 && retry && state.tokens?.refreshToken){
    const refresh=await fetch('/api/v1/auth/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refreshToken:state.tokens.refreshToken})});
    const result=await refresh.json();
    if(refresh.ok){storeAuth(result.data,state.user);return api(path,options,false)}
  }
  if(!response.ok){const error=new Error(data.message||'请求失败');error.requestId=data.requestId;error.status=response.status;throw error}
  state.offline=false;badge();
  if(response.status===202)return null;
  return data.data;
}
async function reload(){
  try{const r=await fetch('/health');const d=await r.json();state.health=d.data;state.offline=false}catch{state.offline=true}
  badge();if(!state.tokens){render();return}
  try{
    const [user,profiles,sessions,resumes]=await Promise.all([api('/users/me'),api('/profiles?limit=50'),api('/sessions?limit=50'),api('/resumes?limit=50')]);
    state.user=user;state.profiles=profiles.items;state.sessions=sessions.items;state.historyCursor=sessions.nextCursor;state.resumes=resumes.items;state.newProfile=false;
    storeAuth(state.tokens,user);cache('profiles',state.profiles);cache('sessions',state.sessions);cache('resumes',state.resumes);
  }catch(error){
    if(error.status===401){clearAuth();showAuth();toast('登录已过期，请重新登录')}else{state.offline=true;toast(error.message)}
    state.profiles=cached('profiles',[]);state.sessions=cached('sessions',[]);state.resumes=cached('resumes',[]);
  }
  $('#history-count').textContent=state.sessions.length;badge();render();
}
function clearAuth(){
  detachStream();state.epoch++;
  if(state.user){const prefix=cacheKey('');Object.keys(localStorage).filter(k=>k.startsWith(prefix)).forEach(k=>localStorage.removeItem(k))}
  sessionStorage.removeItem('hc-tokens');sessionStorage.removeItem('hc-user');sessionStorage.removeItem('hc-pending');
  Object.assign(state,{tokens:null,user:null,profiles:[],resumes:[],sessions:[],session:null,messages:[],report:null,weak:[],memories:[],enabled:true,page:'home',busy:false,createAttempt:null,profileAttempt:null});updateAccount();render();
}
function showAuth(){state.authMode='login';renderAuth();$('#auth-error').textContent='';if(!$('#auth-dialog').open)$('#auth-dialog').showModal()}
function renderAuth(){$$('#auth-tabs button').forEach(b=>b.classList.toggle('selected',b.dataset.auth===state.authMode));$('#auth-title').textContent=state.authMode==='login'?'欢迎回来':'开启你的练习空间';$('#nickname-label').hidden=state.authMode!=='register';$('#auth-password').minLength=state.authMode==='register'?8:1;$('#auth-password').autocomplete=state.authMode==='register'?'new-password':'current-password';$('#auth-submit').textContent=state.authMode==='login'?'登录并开始练习 →':'创建账号并开始练习 →'}
$('#auth-tabs').addEventListener('click',e=>{if(e.target.dataset.auth){state.authMode=e.target.dataset.auth;renderAuth()}});
$('#auth-close').onclick=()=>$('#auth-dialog').close();
$('#auth-form').onsubmit=async e=>{e.preventDefault();const submit=$('#auth-submit');submit.disabled=true;$('#auth-error').textContent='';
  const account=$('#auth-account').value.trim(),password=$('#auth-password').value;
  try{if(state.authMode==='register')await api('/auth/register',{method:'POST',body:{account,password,nickname:$('#auth-nickname').value.trim()||'新同学'}});
    const tokens=await api('/auth/login',{method:'POST',body:{account,password,clientType:'web'}});storeAuth(tokens,tokens.user);$('#auth-dialog').close();$('#auth-password').value='';state.page='home';await reload();toast('欢迎回来，开始你的下一次练习吧。');
  }catch(error){$('#auth-error').textContent=error.message+(error.requestId?' · '+error.requestId.slice(-8):'')}finally{submit.disabled=false}
};
$('#account-button').onclick=async()=>{if(!state.user)return showAuth();if(confirm('退出当前账号？将清除该账号在此浏览器中的本地缓存。')){try{await api('/auth/logout',{method:'POST'})}catch{}clearAuth()}};
$('#refresh-button').onclick=()=>reload();
$$('[data-page]').forEach(b=>b.onclick=()=>navigate(b.dataset.page));

function detachStream(){state.stream?.abort();state.stream=null;state.busy=false;clearTimeout(state.reportTimer)}
async function navigate(page){
  detachStream();state.page=page;render();
  if(!state.user && page!=='home'){showAuth();return}
  try{
    if(page==='history'){const result=await api('/sessions?limit=50');state.sessions=result.items;state.historyCursor=result.nextCursor;cache('sessions',state.sessions);$('#history-count').textContent=state.sessions.length}
    if(page==='weak'){state.weak=(await api('/weak-points?limit=50')).items;cache('weak',state.weak)}
    if(page==='memory'){const [settings,memories]=await Promise.all([api('/users/me/memory-settings'),api('/users/me/memories?limit=50')]);state.enabled=settings.enabled;state.memories=memories.items;cache('memories',state.memories)}
    render();
  }catch(error){if(page==='weak')state.weak=cached('weak',[]);if(page==='memory')state.memories=cached('memories',[]);toast(error.message);render()}
}
function render(){
  const labels={home:'面试训练台',history:'练习记录',session:'模拟面试',report:'面试复盘',weak:'能力提升',memory:'个性化记忆'};
  $('#page-label').textContent=labels[state.page];
  $$('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page||(b.dataset.page==='history'&&['session','report'].includes(state.page))));
  const pages={home:renderHome,history:renderHistory,session:renderSession,report:renderReport,weak:renderWeak,memory:renderMemory};
  $('#main').innerHTML=(state.offline?'<div class="offline-note">当前为离线状态，以下是本账号的本地缓存。新练习与同步将在恢复连接后可用。</div>':'')+pages[state.page]();
  bindPage();
}
function intro(title,subtitle){return `<section class="intro"><div><div class="eyebrow">YOUR NEXT STEP, WITH CONFIDENCE</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><span class="welcome-star">✳</span></section>`}
function renderHome(){
  const completed=state.sessions.filter(s=>s.status==='completed');const scored=completed.filter(s=>Number.isFinite(s.overallScore));const average=scored.length?Math.round(scored.reduce((a,s)=>a+s.overallScore,0)/scored.length):'—';
  const relevant=state.profiles.filter(p=>p.type===state.scene);state.newProfile=state.newProfile||relevant.length===0;
  return intro(`${state.user?state.user.nickname+'，':'准备好了吗，'}让下一次面试更从容。`,'选一个适合你的场景，从一次轻松的模拟开始。')+
    `<section class="stats"><div class="stat"><span class="stat-icon">◷</span><div><strong>${state.sessions.length}</strong><small>次</small><p>最近的面试练习</p></div></div><div class="stat"><span class="stat-icon">✓</span><div><strong>${completed.length}</strong><small>次</small><p>已完成的完整复盘</p></div></div><div class="stat"><span class="stat-icon">↗</span><div><strong>${average}</strong><small>分</small><p>最近练习平均分</p></div></div></section>
    <div class="dashboard-grid"><section class="card"><div class="section-top"><h3>开启一场模拟面试</h3><small>START A NEW PRACTICE</small></div>
    <div class="section-step"><span>1</span>选择面试场景</div><div class="scenario-grid">${[['employment','▣','求职面试','岗位能力 · 项目经历'],['volunteer','♡','志愿者面试','服务意识 · 沟通协作'],['club','✧','社团面试','兴趣表达 · 团队融入']].map(([id,icon,label,desc])=>`<button class="scenario ${state.scene===id?'active':''}" data-scene="${id}"><span class="radio"></span><span class="scene-icon">${icon}</span><strong>${label}</strong><small>${desc}</small></button>`).join('')}</div>
    <form id="setup-form"><div class="section-step"><span>2</span>完善你的面试信息</div>
    <label>${state.scene==='employment'?'目标岗位':state.scene==='volunteer'?'志愿活动':'目标社团'}<input id="target" placeholder="${state.scene==='employment'?'例如：后端开发工程师':state.scene==='volunteer'?'例如：校园迎新志愿者':'例如：机器人社团'}" maxlength="120" required></label>
    <label>${state.scene==='employment'?'岗位描述 / JD（可选）':'场景要求（可选）'}<textarea id="scene-description" rows="2" maxlength="12000" placeholder="补充要求，让提问更贴合这次面试"></textarea></label>
    <div class="link-row"><label style="margin:0">使用的个人画像</label><button type="button" class="text-button" id="new-profile">${state.newProfile&&relevant.length?'选择已有画像':'+ 新建画像'}</button></div>
    ${state.newProfile?`<div class="subtle-panel"><div class="row"><label>画像名称<input id="profile-name" placeholder="我的${sceneNames[state.scene]}画像" maxlength="120"></label><label>学校（可选）<input id="profile-school" maxlength="120" placeholder="例如：示例大学"></label></div><label>技能 / 兴趣（用逗号分隔）<input id="profile-skills" placeholder="例如：Python、沟通协作、活动组织" maxlength="1000"></label><label>相关经历（可选）<textarea id="profile-experience" rows="2" placeholder="说明你参与过的项目或活动，以及承担的职责" maxlength="10000"></textarea></label><p>画像按场景独立保存，练习中使用创建时的快照。</p></div>`:`<select id="profile-select" aria-label="选择个人画像">${relevant.map(p=>`<option value="${esc(p.profileId)}">${esc(p.displayName)} · v${p.version}</option>`).join('')}</select>`}
    <div class="section-step"><span>3</span>添加简历与对话偏好</div><div class="row"><label>简历上下文（可选）<select id="resume-select"><option value="">本次不使用简历</option>${state.resumes.map(r=>`<option value="${esc(r.resumeId)}" ${r.status!=='confirmed'?'disabled':''}>${esc(r.fileName)}${r.status!=='confirmed'?' · 待确认':''}</option>`).join('')}</select></label><label>上传 PDF / Word<input id="resume-upload" type="file" accept=".pdf,.docx"></label></div>
    ${state.resumes.some(r=>r.status!=='confirmed')?'<button type="button" id="review-resume" class="text-button">核对最近一份未确认简历 →</button>':''}
    <div class="segmented" id="modality"><button class="selected" type="button" data-modality="text">◌ 文字对话</button><button type="button" data-modality="voice">♩ 语音辅助</button></div><p class="form-note">语音在设备端转写，核对后作为文字发送。支持的浏览器可使用录音与朗读。</p>
    <p id="setup-error" class="error" role="alert"></p><div class="start-action"><p>围绕你的经历提问，结束后生成专属复盘。</p><button class="primary" id="start-button" type="submit">开始我的面试 <span style="margin-left:20px">→</span></button></div></form></section>
    <aside class="dashboard-aside"><section class="card guide-card"><div class="eyebrow">A LITTLE PRACTICE, A BIG DIFFERENCE</div><h2>在这里练习，<br>在面试中发光。</h2><p>没有标准答案的压力。<br>只有一次次更清楚的表达。</p><div class="orbit"><span>✧</span></div><div class="guide-list"><span>↗</span><div>真实情景提问<br>有依据的评分与建议</div></div></section><section class="card mini-section"><div class="section-top"><h3>最近的练习</h3><button class="text-button" data-go="history">全部 ↗</button></div>${state.sessions.length?state.sessions.slice(0,3).map(historyItem).join(''):'<div class="empty"><span class="empty-symbol">◷</span>第一场练习，从现在开始。<br>你的每一次进步都会留在这里。</div>'}</section></aside></div>`;
}
function historyItem(s){return `<button class="history-item" data-open="${esc(s.sessionId)}"><span><strong>${esc(s.title)}</strong><small>${date(s.updatedAt)}</small></span><span class="tag ${s.status==='completed'?'green':''}">${statusNames[s.status]}</span></button>`}
function renderHistory(){const sessions=state.sessions.filter(s=>state.historyFilter==='all'||s.status===state.historyFilter);return intro('每一次练习，都有迹可循。','回看你的回答与复盘，找到下一次练习的重点。')+`<div class="filter-row">${[['all','全部记录'],['active','进行中'],['completed','已完成'],['cancelled','已取消']].map(([id,name])=>`<button class="filter-chip ${state.historyFilter===id?'selected':''}" data-filter="${id}">${name}</button>`).join('')}</div><div class="history-grid">${sessions.map(s=>`<article class="card history-card"><div class="link-row"><span class="tag ${s.status==='completed'?'green':''}">${statusNames[s.status]}</span><span class="history-score">${s.overallScore??'—'}</span></div><h3>${esc(s.title)}</h3><p class="meta">${sceneNames[s.scene]} · ${date(s.createdAt)}</p><div class="actions"><button class="text-button" data-open="${esc(s.sessionId)}">${s.status==='completed'?'查看复盘':'打开会话'} →</button><button class="icon-button" data-delete-session="${esc(s.sessionId)}" title="删除记录" aria-label="删除${esc(s.title)}">×</button></div></article>`).join('')||'<section class="card empty">还没有这类练习记录，先开启一场面试吧。</section>'}</div>${state.historyCursor?'<button class="secondary load-more" id="load-more">加载更多记录</button>':''}`}
function messageHtml(m){return `<article class="message ${m.role==='user'?'user':''}" id="${esc(m.messageId)}"><span class="message-avatar">${m.role==='user'?esc(state.user?.nickname?.slice(0,1)||'我'):'✧'}</span><div class="bubble-wrap"><div class="message-label">${m.role==='user'?'你':'Hono · 模拟面试官'} <span style="margin-left:8px">${date(m.createdAt)}</span></div><div class="bubble">${esc(m.content)}</div>${m.role==='assistant'?`<button class="text-button" data-speak="${esc(m.messageId)}" style="font-size:9px">♩ 朗读</button>`:''}</div></article>`}
function renderSession(){
  const s=state.session;if(!s)return '<div class="skeleton"></div>';
  const ended=s.status!=='active';const current=stages.indexOf(s.stage);
  return `<section class="intro"><div><div class="eyebrow">IN YOUR OWN WORDS</div><h1>找到表达的节奏。</h1><p>专注于当下的问题，具体说明你做过什么、如何做、结果怎样。</p></div></section>
    ${ended?`<div class="session-banner">${statusNames[s.status]}${s.status==='generating_report'?'，正在整理你的专属复盘。':''} ${s.status==='completed'?'<button class="text-button" id="show-report">查看评分报告 →</button>':s.status==='failed'?'<button class="text-button" id="retry-report">重新生成报告 →</button>':''}</div>`:''}
    <div class="session-layout"><section class="card chat-card"><div class="chat-header"><div><h3>${esc(s.title)}</h3><p>${sceneNames[s.scene]} · 画像 v${s.profileSnapshotVersion} · ${s.modality==='voice'?'语音辅助':'文字对话'}</p></div><div class="actions">${!ended?'<button class="text-button" id="cancel-session">取消练习</button><button class="secondary" id="finish-session">结束并复盘 ↗</button>':'<button class="secondary" data-go="history">返回记录</button>'}</div></div><div class="transcript" id="transcript">${state.messages.map(messageHtml).join('')}</div><div id="agent-state" class="agent-state ${state.busy?'busy':''}" role="status">${state.busy?'面试官正在整理回应…':ended?'练习记录已保存':'轮到你了，慢慢说。'}</div><form class="composer" id="message-form"><textarea id="answer" rows="2" placeholder="${ended?'本次练习已结束，可回看完整对话。':'在这里写下你的回答…'}" maxlength="10000" aria-label="面试回答" ${ended?'disabled':''}></textarea><div class="composer-bottom"><div class="composer-tools"><button class="icon-button" id="record-answer" type="button" title="录音转写" aria-label="录音转写" ${ended?'disabled':''}>♩</button><span id="composer-hint">Ctrl / ⌘ + Enter 发送</span></div><button class="primary" type="submit" id="send-answer" ${ended||state.busy?'disabled':''}>发送回答 ↑</button></div></form></section><aside class="session-aside"><section class="card"><h3>这次面试的旅程</h3><ol class="steps">${stages.map((id,i)=>`<li class="${i===current?'current':i<current?'past':''}"><span>${i<current?'✓':i+1}</span>${stageNames[i]}</li>`).join('')}</ol><div class="side-info"><strong>✧ 一个小提醒</strong>用具体的行动与结果支撑观点。无需追求完美，我们更想听到你真实的思考。</div></section></aside></div>`;
}
function renderReport(){const r=state.report;if(!r)return intro('正在整理你的复盘…','评分会引用本次回答作为证据，请稍候。')+'<div class="skeleton"></div>';
  return `<div class="header-with-button">${intro('把这一次，变成下一次的底气。','从回答中找到优势，也找到可以继续练习的方向。')}<button class="secondary" id="view-transcript">回看对话 ↗</button></div>
    <section class="card report-hero"><div class="score-circle"><strong>${r.overallScore}</strong><small>综合表现 / 100</small></div><div><div class="eyebrow">YOUR INTERVIEW REFLECTION</div><h2>${esc(state.session?.title||'面试复盘')}</h2><p>${esc(r.summary)}</p><p style="margin-top:9px">${r.evaluationSource==='demo'?'本地规则演示评分 · 用于联调，非云端 AI 评价':r.evaluationSource==='insufficient_evidence'?'证据不足，未评估能力':'DeepSeek 云端生成 · 四维等权平均'}</p></div></section>
    <div class="report-grid">${r.dimensions.map(d=>`<article class="card dimension"><div class="dimension-title"><h3>${esc(d.label)}</h3><strong>${d.score}<small style="font:10px sans-serif;margin-left:4px">/100</small></strong></div><div class="progress-track"><div class="progress-fill" style="width:${Number(d.score)}%"></div></div><p><strong>做得好的</strong>${esc(d.strengths.join('；'))}</p><p><strong>可以改进</strong>${esc(d.issues.join('；'))}</p><p><strong>下次试试</strong>${esc(d.suggestions.join('；'))}</p><div class="evidence-row"><button class="text-button" data-evidence="${esc(d.evidence[0]||'')}">查看回答证据 ↗</button><button class="text-button" style="margin-left:auto" data-mark="${d.key}">+ 标记弱项</button></div></article>`).join('')}</div><section class="card mini-section"><div class="section-top"><h3>下一次，带着这些小目标出发</h3><small>NEXT PRACTICE</small></div><ul class="action-list">${r.actionItems.map(item=>`<li>${esc(item)}</li>`).join('')}</ul><div class="actions"><button class="secondary" id="export-record">导出本次记录</button><button class="primary" data-go="home">开始新的练习 →</button></div></section>`;
}
function renderWeak(){return intro('有重点地练习，更快看到进步。','将复盘里的薄弱环节记下来，在下一次面试中继续挑战。')+state.weak.map(w=>`<article class="card memory-card"><div class="memory-top"><span class="tag">${esc(dimensionNames[w.dimensionKey]||w.dimensionKey)}</span><span class="muted small">${date(w.createdAt)}</span></div><h3>${esc(w.note||'从这次回答中继续练习')}</h3><div class="actions"><button class="text-button" data-open="${esc(w.sessionId)}">回看来源会话 →</button><button class="text-button" data-delete-weak="${esc(w.weakPointId)}">取消标记</button></div></article>`).join('')+(state.weak.length?'':'<section class="card empty"><span class="empty-symbol">◎</span>在评分报告中标记弱项，建立你的练习清单。</section>')}
function renderMemory(){return intro('让练习，越来越懂你的方向。','你可以查看、关闭或清除长期记忆。清除记忆不会删除练习记录。')+`<section class="card memory-card"><div class="memory-top"><div><h3>在后续练习中使用历史弱项</h3><p style="margin:0">${state.enabled?'已开启：用于个性化追问，并保存新的复盘摘要。':'已关闭：不读取历史记忆，也不保存新的复盘摘要。'}</p></div><label class="toggle" aria-label="启用长期记忆"><input id="memory-enabled" type="checkbox" ${state.enabled?'checked':''}><span></span></label></div></section>`+state.memories.map(m=>`<article class="card memory-card"><span class="tag">复盘摘要 · ${date(m.createdAt)}</span><h3>${esc(m.content)}</h3><button class="text-button" data-open="${esc(m.source.sessionId)}">查看来源 →</button></article>`).join('')+(!state.memories.length?'<section class="card empty"><span class="empty-symbol">✧</span>目前没有长期记忆。完成面试后，将按你的设置保存维度摘要。</section>':'<div class="actions"><button class="secondary danger" id="clear-memory">清除全部长期记忆</button></div>')}

function bindPage(){
  $$('[data-go]').forEach(b=>b.onclick=()=>navigate(b.dataset.go));
  $$('[data-open]').forEach(b=>b.onclick=()=>openSession(b.dataset.open,true));
  $$('[data-scene]').forEach(b=>b.onclick=()=>{state.scene=b.dataset.scene;state.newProfile=false;render()});
  $$('[data-filter]').forEach(b=>b.onclick=()=>{state.historyFilter=b.dataset.filter;render()});
  $('#new-profile')?.addEventListener('click',()=>{state.newProfile=!state.newProfile;render()});
  $('#setup-form')?.addEventListener('submit',startSession);
  $$('#modality button').forEach(b=>b.onclick=()=>{$$('#modality button').forEach(x=>x.classList.remove('selected'));b.classList.add('selected')});
  $('#resume-upload')?.addEventListener('change',uploadResume);
  $('#review-resume')?.addEventListener('click',()=>reviewResume(state.resumes.find(r=>r.status!=='confirmed').resumeId));
  $('#message-form')?.addEventListener('submit',sendMessage);
  $('#answer')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('#message-form').requestSubmit()}});
  $('#finish-session')?.addEventListener('click',finishSession);
  $('#cancel-session')?.addEventListener('click',cancelSession);
  $('#show-report')?.addEventListener('click',()=>showReport());$('#retry-report')?.addEventListener('click',finishSession);
  $('#view-transcript')?.addEventListener('click',()=>{state.page='session';render();scrollChat()});
  $('#export-record')?.addEventListener('click',exportRecord);
  $('#record-answer')?.addEventListener('click',recordAnswer);
  $$('[data-speak]').forEach(b=>b.onclick=()=>speak(b.dataset.speak));
  $$('[data-evidence]').forEach(b=>b.onclick=()=>{const id=b.dataset.evidence;if(!id)return toast('本次没有可引用的用户回答');state.page='session';render();const el=document.getElementById(id);el?.scrollIntoView({behavior:'smooth',block:'center'});el?.classList.add('highlight')});
  $$('[data-mark]').forEach(b=>b.onclick=async()=>{const dimension=state.report.dimensions.find(x=>x.key===b.dataset.mark);try{await api(`/sessions/${state.session.sessionId}/weak-points`,{method:'POST',body:{dimensionKey:dimension.key,messageIds:dimension.evidence,note:dimension.suggestions[0]}});toast('已加入能力提升清单')}catch(e){toast(e.message)}});
  $$('[data-delete-weak]').forEach(b=>b.onclick=async()=>{try{await api('/weak-points/'+b.dataset.deleteWeak,{method:'DELETE'});await navigate('weak')}catch(e){toast(e.message)}});
  $$('[data-delete-session]').forEach(b=>b.onclick=async()=>{const s=state.sessions.find(x=>x.sessionId===b.dataset.deleteSession);if(['active','generating_report'].includes(s.status))return toast('请先结束或取消会话');if(!confirm('删除这次会话及其消息、报告和关联弱项？'))return;try{await api('/sessions/'+s.sessionId,{method:'DELETE'});localStorage.removeItem(cacheKey('session:'+s.sessionId));localStorage.removeItem(cacheKey('messages:'+s.sessionId));localStorage.removeItem(cacheKey('report:'+s.sessionId));await reload()}catch(e){toast(e.message)}});
  $('#load-more')?.addEventListener('click',async()=>{try{const page=await api('/sessions?limit=50&cursor='+encodeURIComponent(state.historyCursor));const ids=new Set(state.sessions.map(s=>s.sessionId));state.sessions.push(...page.items.filter(s=>!ids.has(s.sessionId)));state.historyCursor=page.nextCursor;cache('sessions',state.sessions);render()}catch(e){toast(e.message)}});
  $('#memory-enabled')?.addEventListener('change',async e=>{try{state.enabled=(await api('/users/me/memory-settings',{method:'PATCH',body:{enabled:e.target.checked}})).enabled;render()}catch(error){e.target.checked=!e.target.checked;toast(error.message)}});
  $('#clear-memory')?.addEventListener('click',async()=>{if(!confirm('清除所有长期记忆摘要？练习记录仍会保留。'))return;try{await api('/users/me/memories',{method:'DELETE'});state.memories=[];cache('memories',[]);render();toast('长期记忆已清除')}catch(e){toast(e.message)}});
}

async function startSession(e){
  e.preventDefault();if(!state.user)return showAuth();const button=$('#start-button');button.disabled=true;$('#setup-error').textContent='';
  try{
    const target=$('#target').value.trim(),description=$('#scene-description').value.trim();
    let profileId=$('#profile-select')?.value;
    if(state.newProfile){const skills=($('#profile-skills').value||'').split(/[,，、]/).map(x=>x.trim()).filter(Boolean);const experience=$('#profile-experience').value.trim();
      const detail=state.scene==='employment'?{targetRole:target,skills,projectExperience:experience?[experience]:[]}:state.scene==='volunteer'?{activityType:target,relevantSkills:skills,volunteerExperience:experience?[experience]:[]}:{targetClub:target,interests:skills,relevantExperience:experience?[experience]:[]};
      const profileBody={type:state.scene,displayName:$('#profile-name').value.trim()||target+'画像',baseInfo:{school:$('#profile-school').value.trim()},detail};
      const profileSignature=JSON.stringify(profileBody);if(state.profileAttempt?.signature!==profileSignature)state.profileAttempt={signature:profileSignature,key:uid()};
      const profile=await api('/profiles',{method:'POST',headers:{'Idempotency-Key':state.profileAttempt.key},body:profileBody});profileId=profile.profileId;if(!state.profiles.some(p=>p.profileId===profileId))state.profiles.unshift(profile);cache('profiles',state.profiles);
    }
    const sceneConfig=state.scene==='employment'?{targetRole:target,jobDescription:description}:state.scene==='volunteer'?{activityType:target,requirements:description}:{targetClub:target,requirements:description};
    const content={mode:'interview',scene:state.scene,sceneConfig,profileId,modality:$('#modality .selected').dataset.modality};if($('#resume-select').value)content.resumeId=$('#resume-select').value;
    const signature=JSON.stringify(content);if(!state.createAttempt||state.createAttempt.signature!==signature)state.createAttempt={signature,key:uid(),clientSessionId:uid()};
    const session=await api('/sessions',{method:'POST',headers:{'Idempotency-Key':state.createAttempt.key},body:{...content,clientSessionId:state.createAttempt.clientSessionId}});state.createAttempt=null;state.profileAttempt=null;state.newProfile=false;
    state.sessions.unshift(session);cache('sessions',state.sessions);await openSession(session.sessionId,false);
  }catch(error){$('#setup-error')&&($('#setup-error').textContent=error.message);toast(error.message)}finally{if(document.contains(button))button.disabled=false}
}
async function uploadResume(e){if(!state.user){e.target.value='';return showAuth()}const file=e.target.files[0];if(!file)return;if(file.size>10*1024*1024)return toast('请上传 10MB 以内的文件');e.target.disabled=true;
  try{const body=new FormData();body.append('file',file);const resume=await api('/resumes',{method:'POST',headers:{'Idempotency-Key':uid()},body});state.resumes.unshift(resume);await reviewResume(resume.resumeId)}catch(error){toast(error.message)}finally{e.target.disabled=false;e.target.value=''}
}
async function reviewResume(id){
  toast('正在提取简历内容，请稍候…');
  try{let result=await api('/resumes/'+id+'/parse');
    for(let i=0;i<80&&['queued','processing'].includes(result.status);i++){await new Promise(resolve=>setTimeout(resolve,400));result=await api('/resumes/'+id+'/parse')}
    if(['queued','processing'].includes(result.status))throw new Error('解析仍在进行，请稍后再次核对');
    state.reviewResumeId=id;const content={education:result.education||[],projects:result.projects||[],skills:result.skills||[],certificates:result.certificates||[]};
    $('#resume-content').value=JSON.stringify(content,null,2);$('#resume-warning').textContent=result.error||result.warnings?.join('；')||'请确认所有字段准确后再保存。';$('#resume-error').textContent='';$('#resume-dialog').showModal();
  }catch(error){toast(error.message)}
}
$('#resume-close').onclick=()=>$('#resume-dialog').close();
$('#resume-form').onsubmit=async e=>{e.preventDefault();const button=$('button[type=submit]',$('#resume-form'));button.disabled=true;try{const body=JSON.parse($('#resume-content').value);await api('/resumes/'+state.reviewResumeId+'/parsed-content',{method:'PATCH',body});await api('/resumes/'+state.reviewResumeId+'/confirm',{method:'POST'});$('#resume-dialog').close();toast('简历内容已确认，可用于面试');state.resumes=(await api('/resumes?limit=50')).items;cache('resumes',state.resumes);const select=$('#resume-select');if(select){select.innerHTML='<option value="">本次不使用简历</option>'+state.resumes.map(r=>`<option value="${esc(r.resumeId)}" ${r.status!=='confirmed'?'disabled':''}>${esc(r.fileName)}${r.status!=='confirmed'?' · 待确认':''}</option>`).join('');select.value=state.reviewResumeId}}catch(error){$('#resume-error').textContent=error instanceof SyntaxError?'JSON 格式有误，请检查逗号、引号和括号。':error.message}finally{button.disabled=false}};

async function openSession(id,preferReport){
  detachStream();state.page='session';state.session=null;state.report=null;render();
  try{const [session,messages]=await Promise.all([api('/sessions/'+id),api('/sessions/'+id+'/messages?limit=50')]);state.session=session;state.messages=messages.items;syncSession(session);cache('session:'+id,session);cache('messages:'+id,state.messages)}
  catch(error){state.session=cached('session:'+id,null);state.messages=cached('messages:'+id,[]);if(!state.session){toast(error.message);state.page='history';render();return}}
  if(preferReport&&state.session.status==='completed'){await showReport();return}
  render();scrollChat();
  if(state.session.activeResponseId&&!state.offline)attachStream(id,state.session.activeResponseId);
  else if(state.session.status==='generating_report')pollReport();
}
function scrollChat(){const el=$('#transcript');if(el)el.scrollTop=el.scrollHeight}
function setBusy(value,label){state.busy=value;const el=$('#agent-state');if(el){el.textContent=label||'轮到你了，慢慢说。';el.classList.toggle('busy',value)}if($('#send-answer'))$('#send-answer').disabled=value||state.session?.status!=='active'}
async function sendMessage(e){e.preventDefault();if(state.busy||state.session?.status!=='active')return;const field=$('#answer');const content=field.value.trim();if(!content)return;
  const id=state.session.sessionId;setBusy(true,'已收到，面试官正在整理回应…');
  try{const result=await api('/sessions/'+id+'/messages',{method:'POST',body:{clientMessageId:uid(),kind:'answer',content,inputMode:state.session.modality}});state.messages.push({messageId:result.userMessageId,sessionId:id,role:'user',kind:'answer',content,inputMode:state.session.modality,stage:state.session.stage,createdAt:new Date().toISOString()});state.lastAnswer=content;cache('messages:'+id,state.messages);render();scrollChat();attachStream(id,result.responseId)}
  catch(error){setBusy(false,error.message);toast(error.message)}
}
function pending(){return readStore('hc-pending',{})}
function savePending(sessionId,value){const items=pending();if(value)items[sessionId]=value;else delete items[sessionId];sessionStorage.setItem('hc-pending',JSON.stringify(items))}
async function attachStream(sessionId,responseId){
  state.stream?.abort();const controller=new AbortController();state.stream=controller;const epoch=state.epoch;let failed=false,completed=false;let lastId=pending()[sessionId]?.responseId===responseId?pending()[sessionId].lastId:null;
  // Replayed deltas start at a known offset; reconcile by replacing that range.
  setBusy(true,'面试官正在思考…');
  for(let attempt=0;attempt<4&&!completed&&!controller.signal.aborted;attempt++){
    try{
      const headers={Authorization:'Bearer '+state.tokens.accessToken};if(lastId)headers['Last-Event-ID']=lastId;
      const response=await fetch(`/api/v1/sessions/${sessionId}/responses/${responseId}/events`,{headers,signal:controller.signal});
      if(!response.ok){const d=await response.json();throw new Error(d.message||'连接失败')}
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      while(!controller.signal.aborted){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let boundary;
        while((boundary=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,boundary).replace(/\r/g,'');buffer=buffer.slice(boundary+2);if(block.startsWith(':'))continue;
          const lines=block.split('\n'),type=lines.find(x=>x.startsWith('event:'))?.slice(6).trim();const raw=lines.filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n');if(!raw)continue;
          const data=JSON.parse(raw),payload=data.payload;if(epoch!==state.epoch)return;
          lastId=data.eventId;savePending(sessionId,{responseId,lastId});
          if(type==='thinking')setBusy(true,'面试官正在思考…');
          if(type==='tool_started')setBusy(true,payload.toolName==='question_bank.search'?'正在检索合适的面试问题…':'正在分析你的场景资料…');
          if(type==='message_delta'){
            let message=state.messages.find(m=>m.messageId===payload.messageId);if(!message){message={messageId:payload.messageId,role:'assistant',content:'',stage:state.session.stage,createdAt:data.timestamp};state.messages.push(message)}
            message.content=Array.from(message.content).slice(0,payload.offset).join('')+payload.delta;
            if(state.page==='session'){const chat=$('#transcript');let article=document.getElementById(payload.messageId);if(!article){chat?.insertAdjacentHTML('beforeend',messageHtml(message));article=document.getElementById(payload.messageId)}if(article)$('.bubble',article).textContent=message.content;scrollChat()}
            setBusy(true,'正在生成回应…');
          }
          if(type==='stage_changed')state.session.stage=payload.stage;
          if(type==='message_completed'){const item=state.messages.find(m=>m.messageId===payload.messageId);if(item){item.content=payload.content;item.stage=payload.stage}cache('messages:'+sessionId,state.messages)}
          if(type==='report_ready'){state.session.status='completed';state.session.reportId=payload.reportId}
          if(type==='error'){failed=true;toast(payload.message);setBusy(false,payload.message)}
          if(type==='done'){completed=true;savePending(sessionId,null);break}
        }
        if(completed){await reader.cancel();break}
      }
      if(!completed&&!controller.signal.aborted)throw new Error('连接中断');
    }catch(error){if(controller.signal.aborted)return;if(attempt===3){toast('连接暂时中断，稍后重新打开会话可继续补取。');setBusy(false,'连接中断；已保存续传位置。');return}setBusy(true,'连接中断，正在补取已生成内容…');await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)))}
  }
  if(controller.signal.aborted||epoch!==state.epoch)return;
  state.stream=null;setBusy(false);
  try{state.session=await api('/sessions/'+sessionId);state.messages=(await api('/sessions/'+sessionId+'/messages?limit=50')).items;syncSession(state.session);cache('session:'+sessionId,state.session);cache('messages:'+sessionId,state.messages);if(state.page==='session'){render();scrollChat();if(failed&&$('#answer'))$('#answer').value=state.lastAnswer||''}if(state.session.status==='generating_report')pollReport();else if(state.session.status==='completed')await showReport()}catch(error){toast(error.message)}
}
async function finishSession(){if(state.busy)return toast('请等待当前回答处理完成');try{await api('/sessions/'+state.session.sessionId+'/finish',{method:'POST',body:{reason:'user_end'}});state.session.status='generating_report';render();pollReport()}catch(error){toast(error.message)}}
async function cancelSession(){if(!confirm('取消本次练习？已保存的对话仍可查看，不会生成报告。'))return;try{await api('/sessions/'+state.session.sessionId+'/cancel',{method:'POST'});detachStream();await openSession(state.session.sessionId,false)}catch(error){toast(error.message)}}
async function pollReport(){clearTimeout(state.reportTimer);const id=state.session?.sessionId;if(!id||state.offline)return;try{const report=await api('/sessions/'+id+'/report');if(report){state.report=report;Object.assign(state.session,{status:'completed',overallScore:report.overallScore,reportId:report.reportId,reportStatus:'ready'});syncSession(state.session);cache('report:'+id,report);cache('session:'+id,state.session);state.page='report';render();return}state.reportTimer=setTimeout(pollReport,900)}catch(error){toast(error.message);state.session.status='failed';if(state.page==='session')render()}}
async function showReport(){detachStream();state.page='report';state.report=cached('report:'+state.session.sessionId,null);render();try{const report=await api('/sessions/'+state.session.sessionId+'/report');if(report){state.report=report;cache('report:'+state.session.sessionId,report);render()}else pollReport()}catch(error){if(!state.report){toast(error.message);state.page='session'}render()}}
function speak(id){if(!window.speechSynthesis)return toast('当前浏览器不支持朗读，请使用鸿蒙客户端');const message=state.messages.find(m=>m.messageId===id);if(!message)return;speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(message.content);utterance.lang='zh-CN';speechSynthesis.speak(utterance)}
function recordAnswer(){const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition)return toast('当前浏览器未提供语音转写，请在鸿蒙端使用语音，或直接输入文字');const recognition=new Recognition();recognition.lang='zh-CN';recognition.interimResults=false;recognition.onresult=e=>{const field=$('#answer');if(field)field.value+=e.results[0][0].transcript;toast('转写完成，请核对文字后发送')};recognition.onerror=()=>toast('无法启用录音，请检查权限或改用文字');recognition.start()}
function exportRecord(){const record={session:state.session,messages:state.messages,report:state.report};const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='honocareer-'+state.session.sessionId+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
window.addEventListener('offline',()=>{state.offline=true;badge();toast('网络已断开，已缓存的练习仍可查看')});
window.addEventListener('online',()=>{toast('网络已恢复，可刷新同步数据');state.offline=false;badge()});
updateAccount();render();reload();
