const boardMetadata = JSON.parse(document.getElementById("board-metadata").textContent || "{}");
let draggedCard=null, originalParent=null, boardDirty=false, saving=false, saveTimer=null, lastPayload="";

function compatibleIds(card){
    return (card.dataset.compatibleBenches||"").split(",").map(v=>v.trim()).filter(Boolean);
}
function laneContainer(lane){ return lane.querySelector(".stack") || lane; }
function canDrop(card,lane){ return lane.dataset.laneType==="pool" || compatibleIds(card).includes(lane.dataset.benchId||""); }
function clearHighlights(){ document.querySelectorAll(".lane").forEach(l=>l.classList.remove("compatible","incompatible")); }
function status(text,state){ const el=document.getElementById("board-status"); el.textContent=text; el.className="status "+state; }
function collect(){
    const pool=[...document.querySelectorAll("#planning-pool-lane .order-card")].map(c=>({order_number:c.dataset.orderNumber}));
    const queues={};
    document.querySelectorAll('.lane[data-lane-type="bench"]').forEach(l => {
    const orders = [...l.querySelectorAll(".order-card")]
        .map(card => ({
            order_number: card.dataset.orderNumber
        }));

        if  (orders.length > 0) {
            queues[l.dataset.benchId] = orders;
        }
    });

    return {planning_pool:pool,manual_queues:queues};
}
function markDirty(){
    boardDirty=true; status("Unsaved changes","saving");
    clearTimeout(saveTimer); saveTimer=setTimeout(()=>savePlanningBoard(false),900);
}
document.querySelectorAll(".order-card").forEach(card=>{
    card.addEventListener("dragstart",e=>{
        draggedCard=card; originalParent=card.parentElement; card.classList.add("dragging");
        document.querySelectorAll(".lane").forEach(l=>l.classList.add(canDrop(card,l)?"compatible":"incompatible"));
        e.dataTransfer.effectAllowed="move";
    });
    card.addEventListener("dragend",()=>{card.classList.remove("dragging");clearHighlights();draggedCard=null;originalParent=null;});
});
document.querySelectorAll(".lane").forEach(lane=>{
    lane.addEventListener("dragover",e=>{
        e.preventDefault();
        if(!draggedCard || !canDrop(draggedCard,lane)) return;
        laneContainer(lane).appendChild(draggedCard);
    });
    lane.addEventListener("drop",e=>{
        e.preventDefault();
        if(!draggedCard) return;
        if(!canDrop(draggedCard,lane)){
            if(originalParent) originalParent.appendChild(draggedCard);
            alert("This order is not compatible with that bench.");
            return;
        }
        markDirty();
    });
});
async function savePlanningBoard(manualSave){
    if(saving) return;
    const payload=JSON.stringify(collect());
    if(!manualSave && payload===lastPayload){boardDirty=false;status("Board saved","saved");return;}
    saving=true;status("Saving and recalculating...","saving");
    try{
        const response=await fetch("/planning-board/save",{method:"POST",headers:{"Content-Type":"application/json"},body:payload});
        const result=await response.json();
        if(!response.ok || !result.success) throw new Error(result.message||"Save failed.");
        lastPayload=payload;boardDirty=false;status("Board saved","saved");
        if(manualSave) location.href="/control?message="+encodeURIComponent(result.message||"Planning Board saved.");
    }catch(error){boardDirty=true;status("Save failed","error");alert(error.message);}
    finally{saving=false;}
}
async function postForm(url,data){
    const response=await fetch(url,{method:"POST",body:data});
    if(!response.ok) throw new Error("Request failed.");
}
async function setStaffing(benchId){
    const data=new FormData();
    data.append("bench_id",benchId);
    data.append("staffing_people",document.getElementById("staff-people-"+benchId).value);
    data.append("staffing_note",document.getElementById("staff-note-"+benchId).value);
    try{await postForm("/staffing/set",data);location.reload();}catch(e){alert(e.message);}
}
async function clearStaffing(benchId){
    const data=new FormData();data.append("bench_id",benchId);
    try{await postForm("/staffing/clear",data);location.reload();}catch(e){alert(e.message);}
}
async function clearAllStaffing(){
    if(!confirm("Clear all temporary staffing changes?")) return;
    try{await postForm("/staffing/clear-all",new FormData());location.reload();}catch(e){alert(e.message);}
}
function openSplitModal(orderNumber){
    document.getElementById("split-order-number").value=orderNumber;
    const ids=(boardMetadata[orderNumber]||{}).compatible_bench_ids||[];
    let count=0;
    document.querySelectorAll(".bench-check").forEach(label=>{
        const show=ids.includes(label.dataset.benchId);
        label.classList.toggle("hidden",!show);
        const cb=label.querySelector("input"); cb.checked=false;
        if(show) count++;
    });
    document.getElementById("split-label").textContent="Splitting order "+orderNumber;
    document.getElementById("split-summary").textContent=count+" compatible open bench(es). Select at least two.";
    document.getElementById("split-modal").classList.add("open");
}
function closeSplitModal(){document.getElementById("split-modal").classList.remove("open");}
window.addEventListener("beforeunload",e=>{if(boardDirty||saving){e.preventDefault();e.returnValue="";}});
lastPayload=JSON.stringify(collect());
