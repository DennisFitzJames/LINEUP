(() => {
  const search=document.getElementById('plan-search'); const status=document.getElementById('status-filter');
  const rows=[...document.querySelectorAll('.operation-row')]; const dateRows=[...document.querySelectorAll('[data-date-row]')];
  function apply(){const q=(search.value||'').trim().toLowerCase(); const s=status.value; rows.forEach(r=>{r.hidden=!((!q||r.dataset.search.includes(q))&&(s==='all'||r.dataset.status===s));}); dateRows.forEach(d=>{let n=d.nextElementSibling,shown=false; while(n&&!n.matches('[data-date-row]')){if(n.matches('.operation-row')&&!n.hidden){shown=true;break}n=n.nextElementSibling;}d.hidden=!shown;});}
  search?.addEventListener('input',apply);status?.addEventListener('change',apply);
  if(location.hash){const target=document.querySelector(location.hash);if(target){setTimeout(()=>{target.scrollIntoView({behavior:'smooth',block:'center'});target.classList.add('flash');},120);}}
})();
