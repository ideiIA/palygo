/* PlayGo — elenco da equipe (nome, RG, técnico e capitão). Compartilhado pelo site e pelo PWA.
   Uso: Elenco.montar(el, { get, post, put, apagar, equipeId, toast }). O RG só chega aqui para quem pode vê-lo (capitão e organização). */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function montar(el, o) {
    const { get, post, put, apagar, equipeId, toast } = o;
    const base = '/equipes/' + equipeId + '/componentes';
    let edit = null;
    let dados = null;

    function linha(c) {
      return '<div class="el-linha' + (c.capitao ? ' capitao' : '') + '"><div class="el-quem"><b>' + esc(c.nome) + '</b>' +
        (c.capitao ? ' <span class="el-tag cap">Capitão</span>' : '') + (c.funcao === 'tecnico' ? ' <span class="el-tag tec">Técnico</span>' : '') +
        '<div class="el-rg">RG ' + esc(c.rg) + '</div></div>' +
        (dados.pode_editar ? '<div class="el-acoes">' + (c.funcao === 'atleta' && !c.capitao ? '<button type="button" data-el="cap" data-id="' + c.id + '" title="Marcar como capitão">★ Capitão</button>' : '') +
          '<button type="button" data-el="ed" data-id="' + c.id + '">Editar</button><button type="button" class="perigo" data-el="rm" data-id="' + c.id + '">Remover</button></div>' : '') + '</div>';
    }

    function formulario() {
      const c = edit ? dados.componentes.find((x) => x.id === edit) : null;
      const semTecnico = !dados.tem_tecnico || (c && c.funcao === 'tecnico');
      return '<form class="el-form" id="el-form-' + equipeId + '"><b>' + (c ? 'Editar componente' : 'Adicionar componente') + '</b>' +
        '<input name="nome" placeholder="Nome completo" maxlength="120" required value="' + esc(c ? c.nome : '') + '">' +
        '<input name="rg" placeholder="RG" maxlength="20" required value="' + esc(c ? c.rg : '') + '">' +
        '<select name="funcao"><option value="atleta"' + (c && c.funcao === 'atleta' ? ' selected' : '') + '>Atleta</option>' +
        (semTecnico ? '<option value="tecnico"' + (c && c.funcao === 'tecnico' ? ' selected' : '') + '>Técnico</option>' : '') + '</select>' +
        '<label class="el-cap"><input type="checkbox" name="capitao"' + (c && c.capitao ? ' checked' : '') + '> É o capitão da equipe</label>' +
        '<div class="el-bts"><button class="el-btn">' + (c ? 'Salvar' : 'Adicionar') + '</button>' + (c ? '<button type="button" class="el-btn suave" data-el="cancelar">Cancelar</button>' : '') + '</div></form>';
    }

    function desenhar() {
      const d = dados;
      if (!d.liberado) { el.innerHTML = '<p class="el-aviso">A organização ainda não liberou o cadastro de componentes.</p>'; return; }
      el.innerHTML = '<div class="el-cab"><b>Elenco</b> <span class="el-cont">' + d.atletas + '/' + d.limite_atletas + ' atletas' + (d.tem_tecnico ? ' + técnico' : '') + '</span></div>' +
        (d.componentes.length ? d.componentes.map(linha).join('') : '<p class="el-aviso">Nenhum componente cadastrado ainda.</p>') +
        (d.pode_editar ? formulario() : '<p class="el-aviso">O elenco está fechado: a equipe já começou a jogar. Fale com a organização para alterações.</p>');
    }

    async function carregar() {
      try { dados = await get(base); desenhar(); } catch (e) { el.innerHTML = '<p class="el-aviso">' + esc(e.message) + '</p>'; }
    }

    el.addEventListener('click', async (ev) => {
      const b = ev.target.closest('[data-el]');
      if (!b) return;
      const acao = b.dataset.el;
      try {
        if (acao === 'ed') { edit = Number(b.dataset.id); desenhar(); }
        else if (acao === 'cancelar') { edit = null; desenhar(); }
        else if (acao === 'cap') { dados = await post(base + '/' + b.dataset.id + '/capitao', {}); desenhar(); }
        else if (acao === 'rm') {
          if (!confirm('Remover este componente do elenco?')) return;
          dados = await apagar(base + '/' + b.dataset.id); edit = null; desenhar();
        }
      } catch (e) { if (toast) toast(e.message); }
    });

    el.addEventListener('submit', async (ev) => {
      const f = ev.target.closest('.el-form');
      if (!f) return;
      ev.preventDefault();
      const corpo = { nome: f.nome.value, rg: f.rg.value, funcao: f.funcao.value, capitao: f.capitao.checked };
      try {
        dados = edit ? await put(base + '/' + edit, corpo) : await post(base, corpo);
        edit = null;
        desenhar();
        if (toast) toast('Elenco atualizado.');
      } catch (e) { if (toast) toast(e.message); }
    });

    carregar();
  }

  window.Elenco = { montar };
})();
