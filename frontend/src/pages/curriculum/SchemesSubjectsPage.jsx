import { useState, useEffect } from 'react';
import curriculumApi from '../../api/curriculumApi';
import academicApi from '../../api/academicApi';
import { useAuth } from '../../context/AuthContext';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, EmptyState } from '../../components/common/StateDisplays';
import { Plus, RefreshCw, BookOpen, Layers, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react';

const STATUS_VARIANT = { DRAFT: 'warning', PUBLISHED: 'success', RETIRED: 'neutral' };

const COURSE_CATEGORIES = [
  { value: 'PCC', label: 'PCC — Program Core Course', kind: 'theory' },
  { value: 'PEC', label: 'PEC — Program Elective Course', kind: 'theory' },
  { value: 'OE', label: 'OE — Open Elective', kind: 'theory' },
  { value: 'MDM', label: 'MDM — Multidisciplinary Minor', kind: 'theory' },
  { value: 'VEC', label: 'VEC — Value Education Course', kind: 'theory' },
  { value: 'PCC_LAB', label: 'PCC Lab — Program Core Course Laboratory', kind: 'lab' },
  { value: 'PROJECT', label: 'Project / Project Phase', kind: 'either' },
  { value: 'INTERNSHIP', label: 'Internship', kind: 'either' },
  { value: 'SEMINAR', label: 'Seminar', kind: 'either' },
];

const categoryKind = (cat) => (COURSE_CATEGORIES.find((c) => c.value === cat)?.kind || 'either');

const pickMark = (o) => (o === null || o === undefined || o === '' ? '—' : o);

/** Exam scheme text for a Subject master row (fields live on the row). */
const subjectExamText = (s) => {
  if (!s) return '—';
  if (s.course_category === 'PCC_LAB') {
    if (s.practical_ca_max_marks == null && s.practical_ese_max_marks == null) return '—';
    return `Pract CA ${pickMark(s.practical_ca_max_marks)} · Pract ESE ${pickMark(s.practical_ese_max_marks)}`;
  }
  if (s.ca_max_marks == null && s.mse_max_marks == null && s.ese_max_marks == null) {
    if (s.practical_ca_max_marks == null && s.practical_ese_max_marks == null) return '—';
    return `Pract CA ${pickMark(s.practical_ca_max_marks)} · Pract ESE ${pickMark(s.practical_ese_max_marks)}`;
  }
  return `CA ${pickMark(s.ca_max_marks)} · MSE ${pickMark(s.mse_max_marks)} · ESE ${pickMark(s.ese_max_marks)}`;
};

/** Exam scheme text for a scheme-subject row (fields nested under subject_). */
const linkExamText = (r) => {
  if (!r) return '—';
  if (r.subject_category === 'PCC_LAB') {
    if (r.subject_practical_ca_max_marks == null && r.subject_practical_ese_max_marks == null) return '—';
    return `Pract CA ${pickMark(r.subject_practical_ca_max_marks)} · Pract ESE ${pickMark(r.subject_practical_ese_max_marks)}`;
  }
  if (r.subject_ca_max_marks == null && r.subject_mse_max_marks == null && r.subject_ese_max_marks == null) {
    if (r.subject_practical_ca_max_marks == null && r.subject_practical_ese_max_marks == null) return '—';
    return `Pract CA ${pickMark(r.subject_practical_ca_max_marks)} · Pract ESE ${pickMark(r.subject_practical_ese_max_marks)}`;
  }
  return `CA ${pickMark(r.subject_ca_max_marks)} · MSE ${pickMark(r.subject_mse_max_marks)} · ESE ${pickMark(r.subject_ese_max_marks)}`;
};

const hoursText = (l, p) => {
  const f = (v) => (v === null || v === undefined || v === '' ? '-' : v);
  return `${f(l)} / ${f(p)}`;
};

export default function SchemesSubjectsPage() {
  const { hasRole } = useAuth();
  const isSysadmin = hasRole('SYSADMIN');

  const [schemes, setSchemes] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [years, setYears] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  const [selectedScheme, setSelectedScheme] = useState(null);
  const [detail, setDetail] = useState(null);

  const [showScheme, setShowScheme] = useState(false);
  const [showSubject, setShowSubject] = useState(false);
  const [showSubjectLink, setShowSubjectLink] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  const [schemeForm, setSchemeForm] = useState({
    code: '', name: '', program: '',
    effective_from_year: '', effective_to_year: '',
    version: 1, min_theory_marks: 20, min_total_marks: 40, max_backlogs_for_atkt: 4,
  });
  const [showYearAdd, setShowYearAdd] = useState(false);
  const [yearForm, setYearForm] = useState({ code: '', name: '', start_date: '', end_date: '' });
  const emptySubjectForm = {
    course_category: '', code: '', title: '',
    lecture_hours: '', practical_hours: '',
    ca_max_marks: '', mse_max_marks: '', ese_max_marks: '',
    practical_ca_max_marks: '', practical_ese_max_marks: '',
    credits: '',
  };
  const [subjectForm, setSubjectForm] = useState(emptySubjectForm);
  const [linkForm, setLinkForm] = useState({ subject: '', semester_number: 1 });

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [schRes, subRes, progRes, yearRes] = await Promise.all([
        curriculumApi.getSchemes(),
        curriculumApi.getSubjects(),
        academicApi.getPrograms().catch(() => ({ data: [] })),
        academicApi.getAcademicYears().catch(() => ({ data: [] })),
      ]);
      const list = schRes.data?.results || schRes.data || [];
      setSchemes(list);
      setSubjects(subRes.data?.results || subRes.data || []);
      setPrograms(progRes.data?.results || progRes.data || []);
      setYears(yearRes.data?.results || yearRes.data || []);
      if (list.length > 0) {
        // Keep current selection if it still exists, else fall back to first.
        // Uses functional update so a just-deleted id never sticks.
        setSelectedScheme((prev) => {
          if (!prev) return list[0].id;
          return list.some((s) => s.id === prev) ? prev : list[0].id;
        });
      } else {
        setSelectedScheme(null);
      }
      return list;
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load schemes & subjects.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  useEffect(() => {
    if (!selectedScheme) { setDetail(null); return; }
    const found = schemes.find((s) => s.id === selectedScheme);
    setDetail(found || null);
  }, [selectedScheme, schemes]);

  const parseErrors = (data) => {
    if (!data || typeof data !== 'object') return {};
    const out = {};
    Object.entries(data).forEach(([k, v]) => { out[k] = Array.isArray(v) ? v.join(' ') : String(v); });
    return out;
  };

  const flash = (msg) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(''), 5000); };

  const loadYears = async (selectId) => {
    try {
      const yearRes = await academicApi.getAcademicYears();
      const list = yearRes.data?.results || yearRes.data || [];
      setYears(list);
      if (selectId) {
        const found = list.find((y) => y.id === selectId);
        if (found) setSchemeForm((prev) => ({ ...prev, effective_from_year: found.id }));
      }
    } catch { /* non-fatal */ }
  };

  const handleCreateYear = async (e) => {
    e.preventDefault();
    setSaving(true); setFieldErrors({});
    try {
      const code = yearForm.code.trim();
      const res = await academicApi.createAcademicYear({
        code,
        name: yearForm.name.trim() || `Academic Year ${code}`,
        start_date: yearForm.start_date,
        end_date: yearForm.end_date,
      });
      setShowYearAdd(false);
      setYearForm({ code: '', name: '', start_date: '', end_date: '' });
      flash(`Academic year ${res.data.code} created and selected.`);
      await loadYears(res.data.id);
    } catch (err) {
      const parsed = parseErrors(err.response?.data);
      if (Object.keys(parsed).length && !err.response?.data?.detail) setFieldErrors(parsed);
      else setError(err.response?.data?.detail || Object.values(parsed).join(' ') || 'Failed to create academic year.');
    } finally { setSaving(false); }
  };

  const handleCreateScheme = async (e) => {
    e.preventDefault();
    setSaving(true); setFieldErrors({});
    try {
      const payload = {
        ...schemeForm,
        code: schemeForm.code.trim(),
        name: schemeForm.name.trim(),
        version: Number(schemeForm.version) || 1,
        min_theory_marks: Number(schemeForm.min_theory_marks),
        min_total_marks: Number(schemeForm.min_total_marks),
        max_backlogs_for_atkt: Number(schemeForm.max_backlogs_for_atkt),
        program: schemeForm.program || null,
        effective_to_year: schemeForm.effective_to_year || null,
      };
      const res = await curriculumApi.createScheme(payload);
      setShowScheme(false);
      setSchemeForm({ code: '', name: '', program: '', effective_from_year: '', effective_to_year: '', version: 1, min_theory_marks: 20, min_total_marks: 40, max_backlogs_for_atkt: 4 });
      flash(`Scheme ${res.data.code} v${res.data.version} created as DRAFT. Publish it to apply to admissions.`);
      await loadAll();
      setSelectedScheme(res.data.id);
    } catch (err) {
      const parsed = parseErrors(err.response?.data);
      if (Object.keys(parsed).length && !err.response?.data?.detail) setFieldErrors(parsed);
      else setError(err.response?.data?.detail || Object.values(parsed).join(' ') || 'Failed to create scheme.');
    } finally { setSaving(false); }
  };

  const numOrNull = (v) => {
    if (v === '' || v === null || v === undefined) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  const handleCreateSubject = async (e) => {
    e.preventDefault();
    setSaving(true); setFieldErrors({});
    try {
      const kind = categoryKind(subjectForm.course_category);
      const payload = {
        course_category: subjectForm.course_category,
        code: subjectForm.code.trim(),
        title: subjectForm.title.trim(),
        lecture_hours: numOrNull(subjectForm.lecture_hours),
        practical_hours: numOrNull(subjectForm.practical_hours),
        credits: numOrNull(subjectForm.credits),
      };
      if (kind === 'lab') {
        payload.practical_ca_max_marks = numOrNull(subjectForm.practical_ca_max_marks);
        payload.practical_ese_max_marks = numOrNull(subjectForm.practical_ese_max_marks);
      } else {
        payload.ca_max_marks = numOrNull(subjectForm.ca_max_marks);
        payload.mse_max_marks = numOrNull(subjectForm.mse_max_marks);
        payload.ese_max_marks = numOrNull(subjectForm.ese_max_marks);
      }
      const res = await curriculumApi.createSubject(payload);
      setShowSubject(false);
      setSubjectForm(emptySubjectForm);
      flash(`Subject ${res.data.code} created with its examination scheme.`);
      await loadAll();
    } catch (err) {
      const parsed = parseErrors(err.response?.data);
      if (Object.keys(parsed).length && !err.response?.data?.detail) setFieldErrors(parsed);
      else setError(err.response?.data?.detail || 'Failed to create subject.');
    } finally { setSaving(false); }
  };

  const handleLinkSubject = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true); setFieldErrors({});
    try {
      // Code, credits & marks auto-fill from the Subject master (no retyping).
      await curriculumApi.createSchemeSubject({
        scheme: selectedScheme,
        subject: linkForm.subject,
        semester_number: Number(linkForm.semester_number),
      });
      setShowSubjectLink(false);
      setLinkForm({ subject: '', semester_number: 1 });
      flash('Subject added to scheme with its examination scheme.');
      await loadAll();
    } catch (err) {
      const data = err.response?.data;
      const parsed = parseErrors(data);
      const visible = {};
      if (parsed.subject) visible.subject = parsed.subject;
      if (parsed.semester_number) visible.semester_number = parsed.semester_number;
      if (data?.non_field_errors) {
        // e.g. duplicate (scheme, semester, course) — show it on the
        // visible Subject field instead of a hidden non-field error.
        const raw = [data.non_field_errors].flat().join(' ');
        visible.subject = /unique|already exists/i.test(raw)
          ? 'This subject is already added to this semester of the scheme.'
          : raw;
      }
      // Any other key (e.g. stale-backend field names) → general line in
      // the popup so the failure is never invisible. Keep the field name
      // so the message is diagnosable.
      const rest = Object.entries(parsed).filter(
        ([k]) => !['subject', 'semester_number', 'non_field_errors', 'detail'].includes(k));
      if (rest.length) visible._general = rest.map(([k, v]) => `${k}: ${v}`).join(' ');
      if (Object.keys(visible).length) setFieldErrors(visible);
      else setError(data?.detail || 'Failed to add subject to scheme.');
    } finally { setSaving(false); }
  };

  const handlePublish = async () => {
    try {
      await curriculumApi.publishScheme(selectedScheme);
      flash('Scheme published. New admissions in its effective years will use it; existing students stay on their entry scheme.');
      await loadAll();
    } catch (err) { setError(err.response?.data?.detail || 'Failed to publish scheme.'); }
  };

  const handleRetire = async () => {
    try {
      await curriculumApi.retireScheme(selectedScheme);
      flash('Scheme retired. It remains attached to existing students/results for history.');
      await loadAll();
    } catch (err) { setError(err.response?.data?.detail || 'Failed to retire scheme.'); }
  };

  const handleDeleteScheme = async (scheme) => {
    const target = typeof scheme === 'object' ? scheme : schemes.find((s) => s.id === scheme);
    if (!target) return;
    // Guard: delete is only offered for DRAFT schemes (enforced again on backend).
    if (target.status !== 'DRAFT') return;
    const subjectCount = target.scheme_subjects?.length || 0;
    const msg = subjectCount > 0
      ? `Delete DRAFT scheme ${target.code} v${target.version} and its ${subjectCount} subject(s)? This cannot be undone.`
      : `Delete DRAFT scheme ${target.code} v${target.version}? This cannot be undone.`;
    if (!window.confirm(msg)) return;
    try {
      await curriculumApi.deleteScheme(target.id);
      flash(`Scheme ${target.code} v${target.version} deleted.`);
      if (selectedScheme === target.id) setSelectedScheme(null);
      await loadAll();
    } catch (err) { setError(err.response?.data?.detail || 'Failed to delete scheme.'); }
  };

  const handleDeleteSubject = async (subject) => {
    if (!subject) return;
    if (!window.confirm(`Delete subject ${subject.code} — ${subject.title}? This cannot be undone.`)) return;
    try {
      await curriculumApi.deleteSubject(subject.id);
      flash(`Subject ${subject.code} deleted.`);
      await loadAll();
    } catch (err) { setError(err.response?.data?.detail || 'Failed to delete subject.'); }
  };

  const handleUnlinkSubject = async (row) => {
    if (!row) return;
    if (!window.confirm(`Remove ${row.course_code} from this DRAFT scheme? The master subject stays.`)) return;
    try {
      await curriculumApi.deleteSchemeSubject(row.id);
      flash(`${row.course_code} removed from scheme.`);
      await loadAll();
    } catch (err) { setError(err.response?.data?.detail || 'Failed to remove subject from scheme.'); }
  };

  const schemeColumns = [
    { header: 'Scheme', render: (s) => <span style={{ fontWeight: 700 }}>{s.code} <span style={{ color: '#64748b' }}>v{s.version}</span></span> },
    { header: 'Name', accessor: 'name' },
    { header: 'Rules', render: (s) => <span style={{ fontSize: '0.8rem' }}>Th≥{s.min_theory_marks} Tot≥{s.min_total_marks} ATKT≤{s.max_backlogs_for_atkt}</span> },
    { header: 'Status', render: (s) => <Badge variant={STATUS_VARIANT[s.status] || 'neutral'}>{s.status_display || s.status}</Badge> },
  ];

  const semGroups = {};
  (detail?.scheme_subjects || []).forEach((ss) => {
    const k = ss.semester_number;
    if (!semGroups[k]) semGroups[k] = [];
    semGroups[k].push(ss);
  });

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Home', to: '/dashboard' }, { label: 'Academics' }, { label: 'Schemes & Subjects' }]}
        title="Schemes & Subjects"
        subtitle="Versioned curriculum rulebooks. Published schemes apply to new admissions; enrolled students keep their entry scheme."
        actions={
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {isSysadmin && (
              <>
                <button className="edvana-btn" onClick={() => { setFieldErrors({}); setSubjectForm(emptySubjectForm); setShowSubject(true); }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', background: 'rgba(255,255,255,0.16)', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', borderRadius: '8px', fontWeight: 600, fontSize: '0.8125rem', padding: '0.5rem 1rem' }}>
                  <BookOpen size={15} /><span>New Subject</span>
                </button>
                <button className="edvana-btn" onClick={() => { setFieldErrors({}); setShowScheme(true); }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', background: '#ffffff', color: '#1d4ed8', borderRadius: '8px', fontWeight: 600, fontSize: '0.8125rem', padding: '0.5rem 1rem' }}>
                  <Plus size={15} /><span>New Scheme</span>
                </button>
              </>
            )}
            <button className="edvana-btn" onClick={loadAll}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', background: 'rgba(255,255,255,0.16)', color: '#ffffff', border: '1px solid rgba(255,255,255,0.3)', borderRadius: '8px', fontWeight: 600, fontSize: '0.8125rem', padding: '0.5rem 1rem' }}>
              <RefreshCw size={15} /><span>Refresh</span>
            </button>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {successMsg && (
          <div style={{ marginBottom: '1rem', padding: '0.9rem 1.1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <CheckCircle2 size={18} />{successMsg}
          </div>
        )}
        {error && (
          <div style={{ marginBottom: '1rem', padding: '0.9rem 1.1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <AlertCircle size={18} />{error}
          </div>
        )}

        {loading ? (
          <div className="edvana-card"><div className="edvana-card-body" style={{ padding: '2rem' }}><LoadingState message="Loading schemes..." /></div></div>
        ) : (
          <>
            <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
              <div className="edvana-card-header"><h2 className="edvana-card-title">Scheme Versions ({schemes.length})</h2>
                <p className="edvana-card-description">Select a scheme to see its semester-wise subjects and rules.</p></div>
              <div className="edvana-card-body" style={{ padding: 0 }}>
                {schemes.length === 0 ? (
                  <div style={{ padding: '2rem' }}><EmptyState title="No schemes yet" message="Sysadmin creates the first scheme version (e.g. G v1) for a program and admission year." /></div>
                ) : (
                  <DataTable columns={[...schemeColumns, {
                    header: 'Open', align: 'right', render: (s) => (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                        <button className="edvana-btn edvana-btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                          onClick={() => setSelectedScheme(s.id)}>View</button>
                        {isSysadmin && s.status === 'DRAFT' && (
                          <button
                            title={`Delete DRAFT scheme ${s.code} v${s.version}`}
                            onClick={() => handleDeleteScheme(s)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', padding: '0.35rem', display: 'inline-flex', alignItems: 'center' }}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </span>
                    ) }]} data={schemes} keyExtractor={(s) => s.id} pageSize={8} />
                )}
              </div>
            </div>

            {detail && (
              <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
                <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                  <div>
                    <h2 className="edvana-card-title">{detail.code} v{detail.version} — {detail.name}</h2>
                    <p className="edvana-card-description">
                      Effective {detail.from_year_code}{detail.to_year_code ? ` → ${detail.to_year_code}` : '+'} ·
                      Pass Th≥{detail.min_theory_marks} Tot≥{detail.min_total_marks} · ATKT≤{detail.max_backlogs_for_atkt} ·
                      {' '}{detail.scheme_subjects?.length || 0} subjects
                    </p>
                  </div>
                  {isSysadmin && (
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      {detail.status === 'DRAFT' && (
                        <button className="edvana-btn edvana-btn-primary" onClick={handlePublish}>Publish</button>
                      )}
                      {detail.status === 'PUBLISHED' && (
                        <button className="edvana-btn edvana-btn-secondary" onClick={handleRetire}>Retire</button>
                      )}
                      {detail.status === 'DRAFT' && (
                        <button className="edvana-btn edvana-btn-secondary" onClick={() => { setFieldErrors({}); setShowSubjectLink(true); }}>
                          <Layers size={14} /> Add Subject
                        </button>
                      )}
                      {detail.status === 'DRAFT' && (
                        <button
                          title={`Delete DRAFT scheme ${detail.code} v${detail.version}`}
                          onClick={() => handleDeleteScheme(detail)}
                          style={{ background: 'none', border: '1px solid #fecaca', cursor: 'pointer', color: '#b91c1c', padding: '0.45rem', display: 'inline-flex', alignItems: 'center', borderRadius: '8px' }}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <div className="edvana-card-body">
                  {Object.keys(semGroups).length === 0 ? (
                    <EmptyState title="No subjects in this scheme" message="Add subjects from the Subject master — just pick the subject and semester." />
                  ) : (
                    Object.keys(semGroups).sort((a, b) => a - b).map((sem) => (
                      <div key={sem} style={{ marginBottom: '1.25rem' }}>
                        <h4 style={{ margin: '0 0 0.5rem' }}>Semester {sem}</h4>
                        <DataTable
                          columns={[
                            { header: 'Course', render: (r) => <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.course_code}</span> },
                            { header: 'Subject', render: (r) => r.subject_title || r.subject_code },
                            { header: 'Credits', accessor: 'credits' },
                            { header: 'Marks', accessor: 'total_marks' },
                            { header: 'Exam Scheme', render: (r) => (
                              <span style={{ fontSize: '0.8rem' }}>{linkExamText(r)}</span>
                            ) },
                            ...(isSysadmin && detail.status === 'DRAFT' ? [{
                              header: '', align: 'right', render: (r) => (
                                <button
                                  title={`Remove ${r.course_code} from scheme`}
                                  onClick={() => handleUnlinkSubject(r)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', padding: '0.35rem', display: 'inline-flex', alignItems: 'center' }}
                                >
                                  <Trash2 size={16} />
                                </button>
                              ),
                            }] : []),
                          ]}
                          data={semGroups[sem]} keyExtractor={(r) => r.id} pageSize={10}
                        />
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            <div className="edvana-card">
              <div className="edvana-card-header"><h2 className="edvana-card-title">Subject Master ({subjects.length})</h2>
                <p className="edvana-card-description">Reusable subjects placed into scheme versions.</p></div>
              <div className="edvana-card-body" style={{ padding: 0 }}>
                <DataTable
                  columns={[
                    { header: 'Code', render: (s) => <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{s.code}</span> },
                    { header: 'Name', accessor: 'title' },
                    { header: 'Category', render: (s) => <span style={{ fontSize: '0.8rem' }}>{s.category_display || s.course_category || '—'}</span> },
                    { header: 'L / P', render: (s) => <span style={{ fontSize: '0.8rem' }}>{hoursText(s.lecture_hours, s.practical_hours)}</span> },
                    { header: 'Exam Scheme', render: (s) => <span style={{ fontSize: '0.8rem' }}>{subjectExamText(s)}</span> },
                    { header: 'Credit', accessor: 'credits' },
                    ...(isSysadmin ? [{
                      header: '', align: 'right', render: (s) => (
                        <button
                          title={`Delete subject ${s.code}`}
                          onClick={() => handleDeleteSubject(s)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c', padding: '0.35rem', display: 'inline-flex', alignItems: 'center' }}
                        >
                          <Trash2 size={16} />
                        </button>
                      ),
                    }] : []),
                  ]}
                  data={subjects} keyExtractor={(s) => s.id} pageSize={10}
                  emptyTitle="No subjects" emptyMessage="Create subjects first, then link them into a scheme."
                />
              </div>
            </div>
          </>
        )}
      </div>

      <Modal isOpen={showScheme} onClose={() => setShowScheme(false)} title="New Scheme Version (Sysadmin)" size="lg"
        footer={<><button className="edvana-btn edvana-btn-secondary" onClick={() => setShowScheme(false)} disabled={saving}>Cancel</button>
          <button className="edvana-btn edvana-btn-primary" onClick={handleCreateScheme} disabled={saving}>{saving ? 'Creating...' : 'Create DRAFT'}</button></>}>
        <form onSubmit={handleCreateScheme}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <FormField label="Scheme Code" required error={fieldErrors.code}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="G" value={schemeForm.code} onChange={(e) => setSchemeForm({ ...schemeForm, code: e.target.value })} />
            </FormField>
            <FormField label="Name" required error={fieldErrors.name}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="G Scheme" value={schemeForm.name} onChange={(e) => setSchemeForm({ ...schemeForm, name: e.target.value })} />
            </FormField>
            <FormField label="Program" required={false} error={fieldErrors.program}
              help="Leave as All programs unless the scheme is program-specific">
              <select className="edvana-input" style={{ width: '100%' }} value={schemeForm.program} onChange={(e) => setSchemeForm({ ...schemeForm, program: e.target.value })}>
                <option value="">All programs (applies to every program)</option>
                {programs.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select>
            </FormField>
            <FormField label="Effective From Year" required error={fieldErrors.effective_from_year}>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select className="edvana-input" style={{ width: '100%' }} value={schemeForm.effective_from_year} onChange={(e) => setSchemeForm({ ...schemeForm, effective_from_year: e.target.value })}>
                  <option value="">Select year</option>
                  {years.map((y) => <option key={y.id} value={y.id}>{y.code}</option>)}
                </select>
                <button type="button" className="edvana-btn edvana-btn-secondary" title="Add a new academic year"
                  style={{ whiteSpace: 'nowrap', padding: '0 0.8rem' }}
                  onClick={() => { setFieldErrors({}); setShowYearAdd(true); }}>
                  + New
                </button>
              </div>
            </FormField>
            <FormField label="Effective To Year (blank = open)" error={fieldErrors.effective_to_year}>
              <select className="edvana-input" style={{ width: '100%' }} value={schemeForm.effective_to_year} onChange={(e) => setSchemeForm({ ...schemeForm, effective_to_year: e.target.value })}>
                <option value="">Open-ended</option>
                {years.map((y) => <option key={y.id} value={y.id}>{y.code}</option>)}
              </select>
            </FormField>
            <FormField label="Version" required error={fieldErrors.version}>
              <input type="number" min="1" className="edvana-input" style={{ width: '100%' }} value={schemeForm.version} onChange={(e) => setSchemeForm({ ...schemeForm, version: e.target.value })} />
            </FormField>
            <FormField label="Min Theory" required error={fieldErrors.min_theory_marks}>
              <input type="number" step="0.5" className="edvana-input" style={{ width: '100%' }} value={schemeForm.min_theory_marks} onChange={(e) => setSchemeForm({ ...schemeForm, min_theory_marks: e.target.value })} />
            </FormField>
            <FormField label="Min Total" required error={fieldErrors.min_total_marks}>
              <input type="number" step="0.5" className="edvana-input" style={{ width: '100%' }} value={schemeForm.min_total_marks} onChange={(e) => setSchemeForm({ ...schemeForm, min_total_marks: e.target.value })} />
            </FormField>
            <FormField label="Max Backlogs (ATKT)" required error={fieldErrors.max_backlogs_for_atkt}>
              <input type="number" min="0" max="12" className="edvana-input" style={{ width: '100%' }} value={schemeForm.max_backlogs_for_atkt} onChange={(e) => setSchemeForm({ ...schemeForm, max_backlogs_for_atkt: e.target.value })} />
            </FormField>
          </div>
        </form>
      </Modal>

      <Modal isOpen={showSubject} onClose={() => setShowSubject(false)} title="New Subject (Sysadmin)" size="lg"
        footer={<><button className="edvana-btn edvana-btn-secondary" onClick={() => setShowSubject(false)} disabled={saving}>Cancel</button>
          <button className="edvana-btn edvana-btn-primary" onClick={handleCreateSubject} disabled={saving}>{saving ? 'Creating...' : 'Create'}</button></>}>
        <form onSubmit={handleCreateSubject}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <FormField label="Course Category" required error={fieldErrors.course_category}>
              <select className="edvana-input" style={{ width: '100%' }} value={subjectForm.course_category} onChange={(e) => setSubjectForm({ ...subjectForm, course_category: e.target.value })}>
                <option value="">Select category</option>
                {COURSE_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </FormField>
            <FormField label="Course Code" required error={fieldErrors.code}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="25AF1245PC302" value={subjectForm.code} onChange={(e) => setSubjectForm({ ...subjectForm, code: e.target.value })} />
            </FormField>
            <FormField label="Course Name" required error={fieldErrors.title}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="Data Structures" value={subjectForm.title} onChange={(e) => setSubjectForm({ ...subjectForm, title: e.target.value })} />
            </FormField>
          </div>
          <div style={{ marginTop: '1rem', background: '#eff6ff', borderRadius: '8px', padding: '0.75rem 1rem 1rem' }}>
            <h4 style={{ margin: '0 0 0.75rem', color: '#1d4ed8', fontSize: '0.9rem' }}>Weekly Hours</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
              <FormField label="L (Lecture)" required error={fieldErrors.lecture_hours}>
                <input type="number" min="0" max="12" className="edvana-input" style={{ width: '100%' }} placeholder="3" value={subjectForm.lecture_hours} onChange={(e) => setSubjectForm({ ...subjectForm, lecture_hours: e.target.value })} />
              </FormField>
              <FormField label="P (Practical)" required error={fieldErrors.practical_hours}>
                <input type="number" min="0" max="24" className="edvana-input" style={{ width: '100%' }} placeholder="-" value={subjectForm.practical_hours} onChange={(e) => setSubjectForm({ ...subjectForm, practical_hours: e.target.value })} />
              </FormField>
            </div>
          </div>
          <div style={{ marginTop: '1rem', background: '#eff6ff', borderRadius: '8px', padding: '0.75rem 1rem 1rem' }}>
            <h4 style={{ margin: '0 0 0.75rem', color: '#1d4ed8', fontSize: '0.9rem' }}>Examination Scheme</h4>
            {categoryKind(subjectForm.course_category) === 'lab' ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
                <FormField label="Practical CA" required error={fieldErrors.practical_ca_max_marks} help="Continuous lab assessment (term work)">
                  <input type="number" step="0.5" min="0" className="edvana-input" style={{ width: '100%' }} value={subjectForm.practical_ca_max_marks} onChange={(e) => setSubjectForm({ ...subjectForm, practical_ca_max_marks: e.target.value })} />
                </FormField>
                <FormField label="Practical ESE" required error={fieldErrors.practical_ese_max_marks} help="End-semester practical / oral exam">
                  <input type="number" step="0.5" min="0" className="edvana-input" style={{ width: '100%' }} value={subjectForm.practical_ese_max_marks} onChange={(e) => setSubjectForm({ ...subjectForm, practical_ese_max_marks: e.target.value })} />
                </FormField>
                <FormField label="Credit" required error={fieldErrors.credits}>
                  <input type="number" min="1" max="12" className="edvana-input" style={{ width: '100%' }} value={subjectForm.credits} onChange={(e) => setSubjectForm({ ...subjectForm, credits: e.target.value })} />
                </FormField>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
                <FormField label="CA (Continuous Assessment)" required error={fieldErrors.ca_max_marks}>
                  <input type="number" step="0.5" min="0" className="edvana-input" style={{ width: '100%' }} value={subjectForm.ca_max_marks} onChange={(e) => setSubjectForm({ ...subjectForm, ca_max_marks: e.target.value })} />
                </FormField>
                <FormField label="MSE (Mid Semester Exam)" required error={fieldErrors.mse_max_marks}>
                  <input type="number" step="0.5" min="0" className="edvana-input" style={{ width: '100%' }} value={subjectForm.mse_max_marks} onChange={(e) => setSubjectForm({ ...subjectForm, mse_max_marks: e.target.value })} />
                </FormField>
                <FormField label="ESE (End Semester Exam)" required error={fieldErrors.ese_max_marks}>
                  <input type="number" step="0.5" min="0" className="edvana-input" style={{ width: '100%' }} value={subjectForm.ese_max_marks} onChange={(e) => setSubjectForm({ ...subjectForm, ese_max_marks: e.target.value })} />
                </FormField>
                <FormField label="Credit" required error={fieldErrors.credits}>
                  <input type="number" min="1" max="12" className="edvana-input" style={{ width: '100%' }} value={subjectForm.credits} onChange={(e) => setSubjectForm({ ...subjectForm, credits: e.target.value })} />
                </FormField>
              </div>
            )}
          </div>
        </form>
      </Modal>

      <Modal isOpen={showSubjectLink} onClose={() => setShowSubjectLink(false)} title="Add Subject to Scheme (DRAFT only)" size="lg"
        footer={<><button type="button" className="edvana-btn edvana-btn-secondary" onClick={() => setShowSubjectLink(false)} disabled={saving}>Cancel</button>
          <button type="button" className="edvana-btn edvana-btn-primary" onClick={handleLinkSubject} disabled={saving}>{saving ? 'Adding...' : 'Add'}</button></>}>
        <form onSubmit={handleLinkSubject}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <FormField label="Subject" required error={fieldErrors.subject}>
              <select className="edvana-input" style={{ width: '100%' }} value={linkForm.subject} onChange={(e) => setLinkForm({ ...linkForm, subject: e.target.value })}>
                <option value="">Select subject</option>
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.title}</option>)}
              </select>
            </FormField>
            <FormField label="Semester (1-8)" required error={fieldErrors.semester_number}>
              <input type="number" min="1" max="8" className="edvana-input" style={{ width: '100%' }} value={linkForm.semester_number} onChange={(e) => setLinkForm({ ...linkForm, semester_number: e.target.value })} />
            </FormField>
          </div>
          <p style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#64748b' }}>
            Course code, credits and examination scheme are taken from the Subject master — no need to type them again.
          </p>
          {fieldErrors._general && (
            <p style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#b91c1c', fontWeight: 600 }}>
              {fieldErrors._general}
            </p>
          )}
        </form>
      </Modal>

      <Modal isOpen={showYearAdd} onClose={() => setShowYearAdd(false)} title="New Academic Year (Sysadmin)"
        footer={<><button className="edvana-btn edvana-btn-secondary" onClick={() => setShowYearAdd(false)} disabled={saving}>Cancel</button>
          <button className="edvana-btn edvana-btn-primary" onClick={handleCreateYear} disabled={saving}>{saving ? 'Creating...' : 'Create & Select'}</button></>}>
        <form onSubmit={handleCreateYear}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
            <FormField label="Year Code" required error={fieldErrors.code} help="e.g. 2027-28">
              <input className="edvana-input" style={{ width: '100%' }} placeholder="2027-28"
                value={yearForm.code} onChange={(e) => setYearForm({ ...yearForm, code: e.target.value })} />
            </FormField>
            <FormField label="Display Name" error={fieldErrors.name}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="Academic Year 2027-2028"
                value={yearForm.name} onChange={(e) => setYearForm({ ...yearForm, name: e.target.value })} />
            </FormField>
            <FormField label="Start Date" required error={fieldErrors.start_date}>
              <input type="date" className="edvana-input" style={{ width: '100%' }}
                value={yearForm.start_date} onChange={(e) => setYearForm({ ...yearForm, start_date: e.target.value })} />
            </FormField>
            <FormField label="End Date" required error={fieldErrors.end_date}>
              <input type="date" className="edvana-input" style={{ width: '100%' }}
                value={yearForm.end_date} onChange={(e) => setYearForm({ ...yearForm, end_date: e.target.value })} />
            </FormField>
          </div>
        </form>
      </Modal>
    </>
  );
}
