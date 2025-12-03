// main.js - loads services and handles booking interactions (full premium)
document.addEventListener('DOMContentLoaded', ()=>{
  const servicesGrid = document.getElementById('services-grid') || document.getElementById('service-list');
  if(servicesGrid){
    fetch('/api/services').then(r=>r.json()).then(j=>{
      if(!j.ok) return;
      servicesGrid.innerHTML='';
      j.services.forEach(s=>{
        const card = document.createElement('div');
        card.className='bg-white p-5 rounded-lg shadow hover:shadow-lg transition';
        card.setAttribute('data-aos','fade-up');
        card.innerHTML = `<div class="flex items-start gap-4">
          <div class="w-12 h-12 rounded-md bg-indigo-50 text-indigo-600 flex items-center justify-center font-semibold">${s.title.split(' ')[0].slice(0,2)}</div>
          <div><div class="font-semibold">${s.title}</div><div class="text-sm text-slate-500 mt-1">${s.description}</div>
          <div class="mt-3 flex items-center justify-between"><div class="text-indigo-600 font-semibold">${s.starting_price}</div><a href="book_now.html" class="text-sm px-3 py-2 bg-indigo-50 text-indigo-600 rounded-md" onclick="selectService(${s.id})">Book</a></div></div></div>`;
        servicesGrid.appendChild(card);
      });
    }).catch(e=>console.error(e));
  }

  const cta = document.getElementById('cta-whatsapp');
  if(cta){
    cta.href = 'https://wa.me/91' + (localStorage.getItem('admin_wh') || '9823125293');
  }
});

function selectService(id){
  try{ localStorage.setItem('service_id', id); }catch(e){}
}
