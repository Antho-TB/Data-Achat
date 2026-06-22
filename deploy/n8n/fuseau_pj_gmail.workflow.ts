// =====================================================================
// FUSEAU -- Fetch PJ Gmail Achats (PLAN B, equivalent n8n du script Python)
// =====================================================================
// Statut : VALIDE par n8n SDK (valid:true, 3 nodes) -- PAS encore cree dans n8n.
// Creation = GO Antho requis (regle autonomie : creation de ressource).
// Prerequis n8n : credential Gmail OAuth2 (compte Marlene) binde dans l'UI,
//                 + partage reseau monte cote runner n8n sur /data/PJ.
//
// Flux : Gmail Trigger (poll 15 min, label Achats/Fournisseurs, has:attachment,
//        downloadAttachments) -> Code (eclate chaque PJ, filtre extensions,
//        nomme YYYYMMDD_from_subject_fichier) -> Read/Write File (write disque).
//
// Difference avec le Plan A (Python) : pas d'idempotence par manifeste ici --
// le readStatus/label gere le perimetre ; en prod, ajouter un markAsRead ou un
// label "traite" pour eviter les re-telechargements. A trancher selon le canal retenu.
// =====================================================================
import { workflow, node, trigger } from '@n8n/workflow-sdk';

const gmailTrigger = trigger({
  type: 'n8n-nodes-base.gmailTrigger',
  version: 1.3,
  config: {
    name: 'Gmail Achats (poll)',
    parameters: {
      event: 'messageReceived',
      simple: false,
      pollTimes: { item: [{ mode: 'everyX', value: 15, unit: 'minutes' }] },
      filters: { q: 'label:Achats/Fournisseurs has:attachment', readStatus: 'both' },
      options: { downloadAttachments: true, dataPropertyAttachmentsPrefixName: 'attachment_' },
    },
    position: [240, 300],
  },
  output: [{}],
});

const splitAttachments = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Split + Nommer PJ',
    parameters: {
      mode: 'runOnceForEachItem',
      language: 'javaScript',
      jsCode: "const ALLOWED=['pdf','xlsx','xls','csv','docx','doc'];\nconst slug=s=>(s||'').replace(/[\\\\/:*?\"<>|\\r\\n\\t]+/g,'_').replace(/_+/g,'_').slice(0,50);\nconst bin=$binary||{};\nconst j=$json||{};\nconst date=j.date?new Date(j.date):new Date();\nconst ym=date.toISOString().slice(0,7).replace('-','');\nconst ymd=date.toISOString().slice(0,10).replace(/-/g,'');\nconst out=[];\nfor(const key of Object.keys(bin)){\n  if(!key.startsWith('attachment_'))continue;\n  const b=bin[key];\n  const ext=(b.fileExtension||(b.fileName||'').split('.').pop()||'').toLowerCase();\n  if(!ALLOWED.includes(ext))continue;\n  const fname=ymd+'_'+slug(j.from)+'_'+slug(j.subject)+'_'+slug(b.fileName);\n  out.push({json:{subdir:ym,fileName:fname,mime:b.mimeType},binary:{data:b}});\n}\nreturn out;",
    },
    position: [540, 300],
  },
  output: [{ subdir: '202509', fileName: '20250922_frs_po_proforma.pdf' }],
});

const writeFile = node({
  type: 'n8n-nodes-base.readWriteFile',
  version: 1.1,
  config: {
    name: 'Ecrire PJ sur disque',
    parameters: {
      operation: 'write',
      fileName: '=/data/PJ/{{ $json.subdir }}/{{ $json.fileName }}',
      dataPropertyName: 'data',
    },
    position: [840, 300],
  },
  output: [{}],
});

export default workflow('fuseau-pj-gmail', 'FUSEAU -- Fetch PJ Gmail Achats')
  .add(gmailTrigger)
  .to(splitAttachments)
  .to(writeFile);
