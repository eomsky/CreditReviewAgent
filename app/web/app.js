const $=s=>document.querySelector(s);
const esc=v=>{const n=document.createElement("span");n.textContent=String(v??"");return n.innerHTML};
const initialOpinion=`## 사업 및 거래 현황
A기업은 자동차 및 전기차 부품을 제조·판매하는 중견기업으로, 주요 완성차 업체와 안정적인 거래관계를 유지하고 있습니다. 2025년 매출액은 1,680억원으로 전년 대비 12.3% 증가했으며 신규 고객사 수주가 외형 성장의 주요 동력입니다.

## 재무 및 상환능력 분석
2025년 말 부채비율은 108.8%, 유동비율은 152.4%로 단기 유동성은 양호합니다. 영업이익률과 영업활동현금흐름이 개선되고 있으며, 예상 DSCR 1.45배를 감안하면 전반적인 상환능력은 양호한 수준입니다.

## 자금용도 및 상환계획
신청자금은 설비 고도화와 운전자금 보강에 사용될 예정으로 목적이 구체적입니다. 신규 수주에 따른 영업현금 유입을 주된 상환재원으로 제시하고 있으나 만기 집중 위험에 대한 기간 중 모니터링이 필요합니다.

## 주요 위험요인 및 보완사항
전기차 시장 성장 둔화, 고객사 발주 변동, 원자재 가격과 환율 변동이 주요 위험요인입니다. 투자 진행률과 양산 일정, 수주 실적 및 현금흐름을 정기적으로 확인하는 조건이 필요합니다.

## 종합 심사의견
거래처 기반과 개선되는 수익지표, 명확한 자금용도를 고려할 때 여신 취급이 가능할 것으로 판단됩니다. 다만 주요 수주 실적과 현금흐름 모니터링을 여신 조건에 포함하는 것이 타당합니다.`;

const state={caseId:null,conversationId:crypto.randomUUID().replaceAll("-",""),messages:[],attachments:[],busy:false,abort:null,versions:[{id:1,text:initialOpinion,createdAt:"초기 의견"}],versionIndex:0,proposal:null,feedbackMode:false,sort:{key:"name",direction:"asc"},selectedSource:1};
const baseSources=[
 {id:1,name:"여신신청원장",type:"테이블",status:"정보계",columns:["신청번호","기업명","신청금액_백만원","기간_개월","상환방식"],rows:[["2026081700124","A기업 주식회사",5000,36,"만기일시"],["2026081700125","B산업 주식회사",2800,24,"분할상환"]]},
 {id:2,name:"재무제표원장",type:"테이블",status:"정보계",columns:["결산기","매출액","영업이익","자산총계","부채총계","부채비율"],rows:[["2025-12",168000,10400,142000,74000,"108.8%"],["2024-12",149600,8200,131000,71500,"120.2%"]]},
 {id:3,name:"담보정보",type:"테이블",status:"정보계",columns:["담보종류","소재지","감정가","선순위","유효담보가"],rows:[["공장","경기도 화성시",7200,1800,5400]]},
 {id:4,name:"기업기본원장",type:"테이블",status:"정보계",columns:["법인번호","업종","설립일","대표자","종업원수"],rows:[["110111-1234567","자동차부품 제조업","2007-04-18","김대표",342]]},
 {id:5,name:"여신거래내역",type:"테이블",status:"정보계",columns:["기준일","상품","한도","잔액","연체일수"],rows:[["2026-08-16","기업운전자금",3000,2410,0],["2026-08-16","시설자금",4500,3720,0]]},
 {id:6,name:"월별매출추이",type:"테이블",status:"정보계",columns:["기준월","매출액","영업이익","수출비중"],rows:[["2026-06",14620,910,"38.2%"],["2026-05",13980,840,"37.5%"],["2026-04",14110,865,"36.9%"]]},
 {id:7,name:"대표자·주주현황",type:"테이블",status:"정보계",columns:["성명","관계","지분율","변동일"],rows:[["김대표","대표이사","42.5%","2024-03-31"],["A홀딩스","최대주주","31.2%","2024-03-31"]]},
 {id:8,name:"신용평가이력",type:"테이블",status:"정보계",columns:["평가일","등급","PD","평가모형"],rows:[["2026-07-30","BBB+","1.32%","기업중형_v4"],["2025-07-29","BBB","1.71%","기업중형_v4"]]},
 {id:9,name:"A기업 신용조사서",type:"PDF",status:"사용자 업로드",body:"A기업 주식회사는 자동차 전장부품을 주력으로 생산하며 주요 매출처와 장기 공급계약을 유지하고 있다. 최근 전기차 부품 생산라인 증설을 추진하고 있으며 수주잔고는 전년 대비 증가하였다."},
 {id:10,name:"2026년 사업계획",type:"DOCX",status:"사용자 업로드",body:"신규 생산라인은 2026년 4분기 시험가동, 2027년 1분기 양산을 목표로 한다. 투자금액은 총 65억원이며 자기자금과 시설자금대출로 조달할 계획이다."},
 {id:11,name:"추정 현금흐름",type:"XLSX",status:"사용자 업로드",columns:["구분","2026E","2027E","2028E"],rows:[["EBITDA",14800,17100,19200],["원리금상환",8200,9300,9800],["DSCR",1.42,1.51,1.63]]},
 {id:12,name:"공장 전경 및 설비",type:"이미지",status:"사용자 업로드",body:"사용자가 업로드한 현장 사진 또는 화면 캡처의 원본 미리보기"}
];
state.sources=[...baseSources];

function parseOpinion(text){const clean=(text||"").replace(/^```(?:markdown)?|```$/gm,"").trim();const parts=clean.split(/^##\s+/m).filter(Boolean);if(!parts.length)return[{title:"심사의견",body:clean}];return parts.map(part=>{const [title,...lines]=part.split("\n");return{title:title.replace(/^#+\s*/,"").trim(),body:lines.join("\n").trim()}})}
function renderOpinion(text,{streaming=false}={}){const parts=parseOpinion(text),root=$("#opinionContent");root.innerHTML=parts.map((s,i)=>`<section class="opinion-section"><h3>${esc(s.title)}${streaming?`<span class="section-state ${i===parts.length-1?"writing":"done"}">${i===parts.length-1?"작성 중":"반영 완료"}</span>`:""}</h3><p>${esc(s.body).replace(/\n/g,"<br>")}${streaming&&i===parts.length-1?'<i class="stream-cursor"></i>':""}</p></section>`).join("");if(streaming)root.scrollTop=root.scrollHeight}
function renderVersion(){const current=state.versions[state.versionIndex],latest=state.versionIndex===state.versions.length-1,prev=$("#previousOpinionVersion"),next=$("#nextOpinionVersion");$("#currentOpinionVersion").textContent=`V${current.id}${latest?" · 최신":""}`;prev.textContent=`‹ V${Math.max(1,current.id-1)}`;prev.disabled=state.versionIndex===0;next.textContent=`V${current.id+1} ›`;next.disabled=latest;$("#opinionUpdated").textContent=current.createdAt;renderOpinion(current.text)}
function addMessage(role,text){const a=document.createElement("article"),d=document.createElement("div");a.className=role;if(role==="assistant"){const av=document.createElement("span");av.className="avatar";av.textContent="AI";a.append(av)}d.innerHTML=`<p>${esc(text)}</p>`;a.append(d);$("#conversation").append(a);$("#conversation").scrollTop=$("#conversation").scrollHeight;return a}
function addDecision(text){const a=addMessage("assistant",text),box=document.createElement("div");box.className="confirm-actions";box.innerHTML='<button class="primary" data-answer="yes">예</button><button data-answer="no">아니오</button><button data-answer="feedback">반영내용 보완</button>';box.onclick=e=>{const answer=e.target.dataset.answer;if(!answer)return;box.remove();if(answer==="yes")applyOpinion();if(answer==="no"){state.proposal=null;addMessage("user","아니오");addMessage("assistant","알겠습니다. 현재 심사의견은 변경하지 않겠습니다.")}if(answer==="feedback"){state.feedbackMode=true;addMessage("user","반영내용 보완");addMessage("assistant","보완하거나 제외할 내용, 또는 원하는 심사의견 카테고리를 입력해 주세요.");$("#messageInput").focus()}};a.querySelector("div").append(box)}
function setBusy(on){state.busy=on;$("#chatForm").classList.toggle("busy",on);$(".apply-row").classList.toggle("busy",on);$("#copyOpinion").disabled=on;$("#saveOpinion").disabled=on;$("#sendButton").textContent=on?"■":"↑";$("#sendButton").classList.toggle("stop",on)}
function conversationContext(){return state.messages.slice(-10).map(m=>`${m.role==="user"?"사용자":"AI"}: ${m.content}`).join("\n")||"추가 대화 없음"}
function requestProposal(){if(state.busy)return;const userNotes=state.messages.filter(m=>m.role==="user").map(m=>m.content);const categoryNotes=userNotes.filter(v=>/(항목|카테고리|목차|구성|관점|기준)/.test(v));const summary=["현재 대화에서 확인된 추가 정보와 요청사항을 심사의견에 반영합니다.",categoryNotes.length?`요청하신 구성 기준(“${categoryNotes.at(-1)}”)에 맞춰 소제목을 재구성합니다.`:"소제목은 대화의 쟁점에 맞게 재구성하되 여신심사 핵심 판단요소를 유지합니다.","상환능력과 근거 수치, 주요 위험 및 보완조건, 종합 심사의견을 포함합니다."].join("\n");state.proposal={summary,feedback:""};addMessage("user","현재까지 내용 반영");addDecision(`${summary}\n\n이대로 심사의견에 반영할까요?`)}
async function applyOpinion(){if(state.busy||!state.proposal)return;addMessage("user","예, 반영해 주세요.");const progressMessage=addMessage("assistant","확인했습니다. 변경 내용을 새 버전의 심사의견에 반영하고 있습니다…");setBusy(true);$("#opinionProgress").classList.remove("hidden");$("#opinionProgressText").textContent="카테고리와 근거를 구성하는 중…";const pendingId=state.versions.length+1;$("#currentOpinionVersion").textContent=`V${pendingId} · 생성 중`;$("#nextOpinionVersion").disabled=true;$("#previousOpinionVersion").disabled=true;let answer="";try{const prompt=`당신은 기업여신 심사역입니다. 현재 심사의견과 대화 이력을 바탕으로 최종 심사의견 전체를 다시 작성하세요.

[중요 작성 규칙]
- 고정된 목차를 기계적으로 사용하지 말고, 사용자가 대화에서 요청한 카테고리나 현재 핵심 쟁점에 맞춰 소제목을 유연하게 구성합니다.
- 다만 기업여신 심사의 목적을 유지하도록 상환능력과 근거, 주요 위험요인과 보완방안, 최종 종합의견은 반드시 포함합니다.
- 확인되지 않은 사실을 만들지 말고, 미입수 정보는 명시합니다.
- 출력은 각 소제목을 '## 소제목' 형식으로 시작하는 한국어 Markdown 본문만 작성합니다.

[반영안]
${state.proposal.summary}
${state.proposal.feedback?`[사용자 보완요청]\n${state.proposal.feedback}`:""}

[대화]
${conversationContext()}`;answer=await streamLLM([...state.messages,{role:"user",content:prompt}],await attachmentPayloads(),text=>{answer=text;renderOpinion(text,{streaming:true});$("#opinionProgressText").textContent=`V${pendingId} 내용을 실시간 작성 중…`});if(!answer.trim())throw Error("생성된 심사의견이 없습니다.");state.versions.push({id:pendingId,text:answer,createdAt:`${new Date().toLocaleString("ko-KR")} 업데이트`});state.versionIndex=state.versions.length-1;state.proposal=null;state.feedbackMode=false;renderVersion();progressMessage.querySelector("p").textContent=`심사의견 V${pendingId} 반영을 완료했습니다. 변경된 소제목과 내용을 왼쪽에서 확인해 주세요.`}catch(e){progressMessage.querySelector("p").textContent=`심사의견 반영 중 오류가 발생했습니다: ${e.message}`;renderVersion()}finally{$("#opinionProgress").classList.add("hidden");setBusy(false)}}
const filePayload=f=>new Promise((ok,no)=>{const r=new FileReader;r.onload=()=>ok({filename:f.name,mime_type:f.type||"application/octet-stream",data_base64:String(r.result).split(",",2)[1]});r.onerror=no;r.readAsDataURL(f)});
const attachmentPayloads=()=>Promise.all(state.attachments.map(a=>filePayload(a.file)));
async function streamLLM(messages,attachments,onToken){const controller=new AbortController;state.abort=controller;const res=await fetch("/api/v1/chat/completions/stream",{method:"POST",headers:{"Content-Type":"application/json","Accept":"text/event-stream"},signal:controller.signal,body:JSON.stringify({messages,attachments,conversation_id:state.conversationId,case_id:state.caseId,current_review:state.versions[state.versions.length-1].text})});if(!res.ok||!res.body)throw Error(`요청 실패 (${res.status})`);const reader=res.body.getReader(),decoder=new TextDecoder;let buffer="",answer="";while(true){const{value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array,{stream:!done});const lines=buffer.split("\n");buffer=done?"":lines.pop();for(const raw of lines){const line=raw.trim();if(!line||line.startsWith(":"))continue;const event=JSON.parse(line.startsWith("data:")?line.slice(5).trim():line);if(event.type==="meta")state.conversationId=event.conversation_id;if(event.type==="token"){if(event.replace)answer="";answer+=event.content||"";onToken?.(answer)}if(event.type==="error")throw Error(event.detail)}if(done)break}return answer}
async function sendMessage(text){text=text.trim();if(!text||(!state.caseId&&state.caseId!==null)||state.busy)return;addMessage("user",text);state.messages.push({role:"user",content:text});$("#messageInput").value="";if(state.feedbackMode){state.feedbackMode=false;state.proposal={...(state.proposal||{summary:"대화 내용을 심사의견에 반영합니다."}),feedback:text};addDecision(`보완 요청을 반영해 다음과 같이 수정하겠습니다.\n\n- ${text}\n- 사용자가 지정한 카테고리를 우선 적용합니다.\n- 상환능력, 근거, 위험 및 보완방안, 종합의견은 심사 필수요소로 유지합니다.\n\n이대로 심사의견에 반영할까요?`);return}setBusy(true);const a=addMessage("assistant","근거자료와 현재 심사의견을 함께 확인하고 있습니다…"),p=a.querySelector("p");try{const answer=await streamLLM(state.messages,await attachmentPayloads(),t=>{p.textContent=t});p.textContent=answer;state.messages.push({role:"assistant",content:answer});$("#applyHint").textContent="새 대화 내용이 있습니다. 확인 후 심사의견에 반영할 수 있습니다."}catch(e){if(e.name==="AbortError")p.textContent="응답 생성을 중단했습니다.";else p.textContent=`연결 오류: ${e.message}`}finally{setBusy(false)}}

function renderFiles(){$("#pendingFiles").innerHTML=state.attachments.map((a,i)=>`<span class="file-chip">▧ ${esc(a.name)} <button data-remove-file="${i}" type="button">×</button></span>`).join("");$("#dataCountBadge").textContent=state.sources.length}
function addFiles(files){for(const file of files){if(state.attachments.some(a=>a.name===file.name))continue;state.attachments.push({name:file.name,file});const ext=file.name.split(".").pop().toUpperCase(),type=file.type.startsWith("image/")?"이미지":ext;state.sources.push({id:state.sources.length?Math.max(...state.sources.map(s=>s.id))+1:1,name:file.name,type,status:"사용자 업로드",file,body:"사용자가 대화창에서 업로드한 원본 자료"})}renderFiles();$("#applyHint").textContent="새 첨부자료가 있습니다. 대화 후 심사의견에 반영해 주세요."}
function sortedSources(){const q=$("#dataSearch").value.trim().toLowerCase(),items=state.sources.filter(s=>`${s.name} ${s.type} ${s.status}`.toLowerCase().includes(q)),{key,direction}=state.sort;return items.sort((a,b)=>String(a[key]).localeCompare(String(b[key]),"ko")*(direction==="asc"?1:-1))}
function renderSources(){const items=sortedSources();$("#dataSummary").textContent=`${items.length} variables / ${state.sources.length} total`;$("#dataSourceBody").innerHTML=items.map(s=>`<tr data-source="${s.id}" class="${s.id===state.selectedSource?"selected":""}"><td>${String(s.id).padStart(2,"0")}</td><td>${esc(s.name)}</td><td><span class="type">${esc(s.type)}</span></td><td><span class="status ${s.status.includes("업로드")?"upload":""}">${esc(s.status)}</span></td></tr>`).join("");document.querySelectorAll("[data-sort]").forEach(b=>{b.querySelector("i").textContent=state.sort.key===b.dataset.sort?(state.sort.direction==="asc"?"↑":"↓"):""});renderPreview(state.sources.find(s=>s.id===state.selectedSource))}
function renderPreview(s){const root=$("#sourcePreview");if(!s){root.innerHTML='<div class="preview-empty">행을 선택하면 원천자료를 확인할 수 있습니다.</div>';return}const head=`<header class="preview-head"><div><h3>${esc(s.name)}</h3><span>READ ONLY · ${esc(s.type)} · ${esc(s.status)}</span></div></header>`;if(s.type==="테이블"||s.type==="XLSX"){const columns=s.columns||["값"],rows=s.rows||[];root.innerHTML=head+`<div class="query-meta">SELECT * FROM ${s.type==="테이블"?"information_system":"uploaded_workbook"}.${s.name} LIMIT 100;\n-- ${rows.length} rows returned · read only</div><div class="result-grid"><table><thead><tr>${columns.map(c=>`<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;return}if(s.type==="이미지"&&s.file){const url=URL.createObjectURL(s.file);root.innerHTML=head+`<div class="image-preview"><img src="${url}" alt="${esc(s.name)}"></div>`;return}root.innerHTML=head+`<div class="document-preview"><article class="paper"><h2>${esc(s.name)}</h2><p>문서유형: ${esc(s.type)}　자료출처: ${esc(s.status)}</p><h3>원천자료 미리보기</h3><p>${esc(s.body||"업로드 원본 문서의 읽기 전용 미리보기입니다.")}</p><h3>심사 참고사항</h3><p>이 화면은 원천자료 확인용이며 내용을 수정하지 않습니다. AI 답변과 심사의견에 활용된 수치는 반드시 본 자료와 대조할 수 있습니다.</p></article></div>`}
function openDataExplorer(){renderSources();$("#dataExplorerDialog").showModal()}
async function saveOpinion(){const text=state.versions[state.versionIndex].text,name=`심사의견_V${state.versions[state.versionIndex].id}.txt`,blob=new Blob([text],{type:"text/plain;charset=utf-8"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
async function init(){renderVersion();renderFiles();try{const r=await fetch("/api/v1/cases");if(r.ok){const d=await r.json();state.caseId=d.items?.[0]?.id??null}}catch(e){console.warn("사례 초기화 실패",e)}}

$("#previousOpinionVersion").onclick=()=>{if(state.versionIndex>0){state.versionIndex--;renderVersion()}};
$("#nextOpinionVersion").onclick=()=>{if(state.versionIndex<state.versions.length-1){state.versionIndex++;renderVersion()}};
$("#copyOpinion").onclick=()=>navigator.clipboard.writeText(state.versions[state.versionIndex].text);
$("#saveOpinion").onclick=saveOpinion;
$("#updateOpinion").onclick=requestProposal;
$("#dataStatusButton").onclick=openDataExplorer;
$("#closeDataExplorer").onclick=()=>$("#dataExplorerDialog").close();
$("#dataSearch").oninput=renderSources;
document.querySelectorAll("[data-sort]").forEach(b=>b.onclick=()=>{const key=b.dataset.sort;if(state.sort.key===key)state.sort.direction=state.sort.direction==="asc"?"desc":"asc";else state.sort={key,direction:"asc"};renderSources()});
$("#dataSourceBody").onclick=e=>{const row=e.target.closest("tr[data-source]");if(row){state.selectedSource=Number(row.dataset.source);renderSources()}};
$("#chatAttach").onclick=()=>$("#chatFile").click();
$("#chatFile").onchange=e=>{addFiles([...e.target.files]);e.target.value=""};
$("#pendingFiles").onclick=e=>{const i=e.target.dataset.removeFile;if(i===undefined)return;const [removed]=state.attachments.splice(Number(i),1);state.sources=state.sources.filter(s=>!(s.file===removed.file));renderFiles()};
$("#chatForm").onsubmit=e=>{e.preventDefault();if(state.busy)state.abort?.abort();else sendMessage($("#messageInput").value)};
$("#messageInput").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();$("#chatForm").requestSubmit()}};
init();
