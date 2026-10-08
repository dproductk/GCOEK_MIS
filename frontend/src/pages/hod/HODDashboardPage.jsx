import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import academicApi from '../../api/academicApi';
import curriculumApi from '../../api/curriculumApi';
import facultyApi from '../../api/facultyApi';
import studentApi from '../../api/studentApi';
import resultsApi from '../../api/resultsApi';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import DataTable from '../../components/common/DataTable';
import Modal from '../../components/common/Modal';
import Badge from '../../components/common/Badge';
import FormField from '../../components/common/FormField';
import {
  Users,
  Award,
  CheckCircle2,
  UserCheck,
  Building2,
  GraduationCap,
  Layers,
  Plus,
  Edit3,
  Search,
  Filter,
  Info,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Trash2,
  BookOpen,
  AlertCircle,
} from 'lucide-react';

export default function HODDashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [divisions, setDivisions] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [faculties, setFaculties] = useState([]);
  const [students, setStudents] = useState([]);
  const [eligibilities, setEligibilities] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [academicYears, setAcademicYears] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [assignSuccess, setAssignSuccess] = useState(null);

  // Intake cards (AH-import separation, frontend-only grouping) + FY/DSY switch
  const [streamView, setStreamView] = useState('FY'); // 'FY' | 'DSY' — mirrors AdmissionImportPage
  const [selectedIntakeKey, setSelectedIntakeKey] = useState(null);

  // Assign class teacher modal
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [selectedDivision, setSelectedDivision] = useState(null);
  const [selectedFacultyId, setSelectedFacultyId] = useState('');

  // Create Division Modal (screenshot-style: Academic Year + Scheme + Year + Semester + Division + Class Code + Teacher + Strength)
  // Backend truth stays: department, academic_year, semester, name, seat_capacity, class_teacher.
  // Scheme/Year/Class-Code are UI aids only (derived, never persisted) per DATABASE_ARCHITECTURE_V2 Sec 15.
  const [createDivModalOpen, setCreateDivModalOpen] = useState(false);
  // When set, the class/division modal confirms (updates) this existing
  // division instead of creating a new one — prevents extra empty Divs.
  const [confirmingDiv, setConfirmingDiv] = useState(null);
  const [confirmingIntakeKey, setConfirmingIntakeKey] = useState(null);
  const [newDivForm, setNewDivForm] = useState({
    name: 'A',
    semester_id: '',
    academic_year_id: '',
    scheme_id: '',
    year_label: '',
    seat_capacity: 60,
    class_teacher: '',
  });
  const [creatingDiv, setCreatingDiv] = useState(false);
  const [divFormError, setDivFormError] = useState('');

  // Student Division Edit Modal
  const [editDivModalOpen, setEditDivModalOpen] = useState(false);
  const [studentForDivEdit, setStudentForDivEdit] = useState(null);
  const [targetDivId, setTargetDivId] = useState('');
  const [savingStudentDiv, setSavingStudentDiv] = useState(false);
  const [deletingDivId, setDeletingDivId] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkDivId, setBulkDivId] = useState('');
  const [bulkSemId, setBulkSemId] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  // Subject-teacher expansion
  const [expandedDivId, setExpandedDivId] = useState(null);
  const [divSubjects, setDivSubjects] = useState([]);
  const [divScheme, setDivScheme] = useState(null);
  const [divAssignments, setDivAssignments] = useState([]);
  const [loadingSubjects, setLoadingSubjects] = useState(false);
  const [slotDrafts, setSlotDrafts] = useState({});
  const [savingSlot, setSavingSlot] = useState(null);

  // Student list filter states
  const [studentSearch, setStudentSearch] = useState('');
  const [rosterExpandedMap, setRosterExpandedMap] = useState({});
  const [rosterSearchMap, setRosterSearchMap] = useState({});

  const toggleRosterExpand = (divId) => {
    setRosterExpandedMap((prev) => ({ ...prev, [divId]: !prev[divId] }));
  };

  const getInitials = (name) => {
    if (!name) return 'ST';
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  };

  const formatStudentName = (name) => {
    if (!name) return '';
    if (name === name.toUpperCase()) {
      return name
        .toLowerCase()
        .split(' ')
        .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''))
        .join(' ');
    }
    return name;
  };

  const hodRoleAssignment = user?.roles?.find((r) => r.codename === 'HOD');
  const hodDeptId = hodRoleAssignment?.department_id;

  useEffect(() => {
    loadDepartmentData();
  }, []);

  // Clicking outside any intake card (and outside the detail panel) clears selection
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (e.target.closest('[data-intake-card], #hod-intake-detail, [data-keep-selection]')) return;
      // Ignore modal / dropdown interactions
      if (e.target.closest('.edvana-modal, [role="dialog"], select, option')) return;
      setSelectedIntakeKey(null);
      setSelectedIds([]);
      setBulkDivId('');
      setExpandedDivId(null);
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const loadDepartmentData = async () => {
    try {
      setLoading(true);
      setError(null);
      // HOD scope: backend already scopes divisions + faculty to HOD's
      // department, but /students/ is college-wide for faculty roles, so
      // pass department explicitly AND filter client-side below as backup.
      const hodDeptForQuery = user?.roles?.find((r) => r.codename === 'HOD')?.department_id;
      const studentParams = hodDeptForQuery
        ? { page_size: 200, department: hodDeptForQuery }
        : { page_size: 200 };
      const [divRes, deptRes, facRes, stuRes, eligRes, semRes, ayRes, schemeRes] = await Promise.all([
        academicApi.getDivisions(),
        academicApi.getDepartments(),
        facultyApi.getFacultyList(),
        studentApi.getStudents(studentParams),
        resultsApi.getEligibilities(),
        academicApi.getSemesters(),
        academicApi.getAcademicYears(),
        curriculumApi.getSchemes({ page_size: 100 }),
      ]);
      setDivisions(divRes.data?.results || divRes.data || []);
      setDepartments(deptRes.data?.results || deptRes.data || []);
      setFaculties(facRes.data?.results || facRes.data || []);
      setStudents(stuRes.data?.results || stuRes.data || []);
      setEligibilities(eligRes.data?.results || eligRes.data || []);
      setSemesters(semRes.data?.results || semRes.data || []);
      setAcademicYears(ayRes.data?.results || ayRes.data || []);
      setSchemes(schemeRes.data?.results || schemeRes.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load department management records.');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignTeacher = async (e) => {
    e.preventDefault();
    if (!selectedDivision || !selectedFacultyId) return;

    try {
      await academicApi.updateDivision(selectedDivision.id, {
        class_teacher: selectedFacultyId,
      });
      const teacher = deptFaculties.find((f) => String(f.id) === String(selectedFacultyId))
        || faculties.find((f) => String(f.id) === String(selectedFacultyId));
      setAssignSuccess(`Assigned ${teacher?.display_name || 'Faculty'} as Class Teacher for Division ${selectedDivision.name}!`);
      setAssignModalOpen(false);
      await loadDepartmentData();
      setTimeout(() => setAssignSuccess(null), 4000);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to assign class teacher.');
    }
  };

  const handleCreateDivision = async (e) => {
    e.preventDefault();
    setDivFormError('');
    setCreatingDiv(true);
    try {
      const activeYear = academicYears.find((y) => y.is_current) || academicYears[0];
      const deptId =
        hodDeptId ||
        deptDivisions[0]?.department ||
        deptDivisions[0]?.department_id ||
        divisions[0]?.department ||
        divisions[0]?.department_id;

      if (!deptId) {
        throw new Error('Unable to resolve department ID for HOD. Please contact Sysadmin.');
      }

      const payload = {
        department: deptId,
        semester: newDivForm.semester_id,
        academic_year: newDivForm.academic_year_id || activeYear?.id,
        name: newDivForm.name.trim().toUpperCase(),
        seat_capacity: Number(newDivForm.seat_capacity) || 60,
        class_teacher: newDivForm.class_teacher || null,
      };

      if (confirmingDiv) {
        // Confirm flow: update the already-existing division in place —
        // never create a second (empty) division for the same intake.
        await academicApi.updateDivision(confirmingDiv.id, payload);
        if (confirmingIntakeKey) markIntakeConfirmed(confirmingIntakeKey);
        setAssignSuccess(`Class confirmed: Division ${payload.name} finalized for this intake (${payload.seat_capacity} seats).`);
      } else {
        // Create flow: block exact duplicates upfront (same year+sem+name)
        // so an extra empty division can never be added by accident.
        const dupe = divisions.find((d) =>
          String(d.academic_year || d.academic_year_id || '') === String(payload.academic_year) &&
          String(d.semester || d.semester_id || '') === String(payload.semester) &&
          String(d.name || '').toUpperCase() === String(payload.name || '').toUpperCase()
        );
        if (dupe) {
          throw new Error(`Division ${payload.name} already exists for this semester — use Confirm Class to edit it instead of adding a new one.`);
        }
        await academicApi.createDivision(payload);
        setAssignSuccess(`Division ${payload.name} created successfully! Note: Divisions are configured once when student onboarding is done.`);
      }
      setCreateDivModalOpen(false);
      setConfirmingDiv(null);
      setConfirmingIntakeKey(null);
      setNewDivForm({ name: 'B', semester_id: '', academic_year_id: '', scheme_id: '', year_label: '', seat_capacity: 60, class_teacher: '' });
      await loadDepartmentData();
      setTimeout(() => setAssignSuccess(null), 4000);
    } catch (err) {
      setDivFormError(
        err.response?.data?.detail ||
        err.response?.data?.non_field_errors?.[0] ||
        err.message ||
        (confirmingDiv ? 'Failed to confirm class.' : 'Failed to create division.')
      );
    } finally {
      setCreatingDiv(false);
    }
  };

  const handleSaveStudentDivision = async (e) => {
    e.preventDefault();
    if (!studentForDivEdit) return;
    setSavingStudentDiv(true);
    try {
      const res = await studentApi.assignDivision(studentForDivEdit.id, targetDivId || null);
      setAssignSuccess(res.data?.detail || `Updated division for ${studentForDivEdit.display_name}!`);
      setEditDivModalOpen(false);
      setStudentForDivEdit(null);
      await loadDepartmentData();
      setTimeout(() => setAssignSuccess(null), 4000);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update student division.');
    } finally {
      setSavingStudentDiv(false);
    }
  };

  // NOTE: all hooks/memos stay above the loading/error early-returns
  // (rules-of-hooks); early-returns are moved just before the JSX return.
  // Department scoping (HOD dept + AIDS-leak guard) is defined below with the
  // other derived data so handleCreateDivision can close over it.
  const handleDeleteDivision = async (row) => {
    if ((row.enrolled_count ?? 0) > 0) return;
    if (!window.confirm(
      `Delete empty Division ${row.name} (Sem ${row.semester_number || '—'})?\n\n` +
      'Only divisions with zero students can be deleted. This is recorded in the audit trail.'
    )) {
      return;
    }
    try {
      setDeletingDivId(row.id);
      await academicApi.deleteDivision(row.id);
      setAssignSuccess(`Division ${row.name} deleted.`);
      await loadDepartmentData();
      setTimeout(() => setAssignSuccess(null), 4000);
    } catch (err) {
      const data = err.response?.data;
      const msg = typeof data === 'object' && data !== null
        ? (data.detail || Object.values(data).flat().join(' '))
        : 'Failed to delete division.';
      alert(msg || 'Failed to delete division.');
    } finally {
      setDeletingDivId(null);
    }
  };

  // ---- Department scoping (fixes AIDS leak + wrong counts) ----
  // Backend scopes divisions/faculty for HOD, but students endpoint is
  // college-wide, so enforce HOD department client-side as well.
  const hodDepartment = departments.find((d) => String(d.id) === String(hodDeptId));
  const hodDeptCode = hodDepartment?.code;

  const deptDivisions = hodDeptId
    ? divisions.filter((d) => {
        const divDeptId = d.department || d.department_id;
        if (divDeptId && String(divDeptId) === String(hodDeptId)) return true;
        if (hodDeptCode && d.department_code === hodDeptCode) return true;
        // If division has neither id nor code match, exclude when HOD scoped
        return !divDeptId && !d.department_code ? true : false;
      })
    : divisions;

  const deptFaculties = hodDeptId
    ? faculties.filter((f) => {
        if (f.department_id && String(f.department_id) === String(hodDeptId)) return true;
        if (hodDeptCode && f.department_code === hodDeptCode) return true;
        return !f.department_id && !f.department_code ? true : false;
      })
    : faculties;

  const deptStudents = hodDeptCode
    ? students.filter((s) => s.department_code === hodDeptCode)
    : students;

  const deptEligibilities = hodDeptCode
    ? eligibilities.filter((e) => !e.department_code || e.department_code === hodDeptCode)
    : eligibilities;

  // Intake keys this HOD has confirmed, persisted per login + department.
  // A global key leaked CSE confirmations into the AIDS view (same
  // year+sem), so the storage key is scoped and the legacy global entry
  // is dropped on load. Confirm state stays UI-only — the update itself
  // is already audit-trailed on the division.
  const confirmedStorageKey = `hod_confirmed_intakes:${user?.id || user?.username || 'anon'}:${hodDeptCode || 'ALL'}`;
  const [confirmedMap, setConfirmedMap] = useState({});
  useEffect(() => {
    try {
      setConfirmedMap(JSON.parse(localStorage.getItem(confirmedStorageKey) || '{}'));
    } catch {
      setConfirmedMap({});
    }
    try {
      localStorage.removeItem('hod_confirmed_intakes');
    } catch {
      /* storage unavailable — in-memory only */
    }
  }, [confirmedStorageKey]);
  const markIntakeConfirmed = (key) => {
    setConfirmedMap((prev) => {
      const next = { ...prev, [key]: true };
      try {
        localStorage.setItem(confirmedStorageKey, JSON.stringify(next));
      } catch {
        /* storage unavailable — in-memory only */
      }
      return next;
    });
  };

  // ---- Intake cards: separate AH imports frontend-only ----
  // Student carries admission_year_code + admission_type/is_direct_second_year
  // (no import_batch FK), so group by (admission year + stream + semester).
  // Divisions match by semester_number within the HOD department scope.
  const streamFilteredStudents = useMemo(() => {
    if (streamView === 'DSY') return deptStudents.filter((s) => s.is_direct_second_year);
    return deptStudents.filter((s) => !s.is_direct_second_year);
  }, [deptStudents, streamView]);
  const intakeGroups = useMemo(() => {
    const semYear = new Map(semesters.map((s) => [String(s.number), s.year_level]));
    const labelOf = (yl) => ({ 1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year' }[yl] || 'FY');
    const map = new Map();
    for (const s of streamFilteredStudents) {
      const admYear = s.admission_year_code || 'Unknown Year';
      const sem = s.semester_number || s.suggested_semester || 1;
      // Dept-scoped key: CSE and AIDS intakes for the same year+sem are
      // different cards and must never share selection/confirm state.
      const key = `${hodDeptCode || 'ALL'}__${admYear}__${sem}`;
      if (!map.has(key)) map.set(key, { key, admissionYear: admYear, semesterNumber: sem, students: [] });
      map.get(key).students.push(s);
    }
    const groups = [...map.values()].map((g) => {
      const divs = deptDivisions.filter((d) => String(d.semester_number) === String(g.semesterNumber));
      const unassigned = g.students.filter((s) => !s.division_id).length;
      const capacity = divs.reduce((sum, d) => sum + (Number(d.seat_capacity) || 0), 0);
      const filled = divs.reduce((sum, d) => sum + (Number(d.enrolled_count) || 0), 0);
      return { ...g, yearLabel: labelOf(semYear.get(String(g.semesterNumber))), divisions: divs, unassigned, capacity, filled };
    });
    groups.sort((a, b) => String(a.admissionYear).localeCompare(String(b.admissionYear)) || a.semesterNumber - b.semesterNumber);
    return groups;
  }, [streamFilteredStudents, deptDivisions, semesters, hodDeptCode]);
  const selectedIntake = intakeGroups.find((g) => g.key === selectedIntakeKey) || null;
  const selectedIntakeStudents = (() => {
    if (!selectedIntake) return [];
    const q = studentSearch.trim().toLowerCase();
    return selectedIntake.students.filter((s) =>
      !q || `${s.display_name || ''} ${s.enrollment_no || ''} ${s.application_id || ''}`.toLowerCase().includes(q)
    );
  })();

  // Dept-wide student list (backs the scoped table's select-all header)
  const filteredStudents = deptStudents.filter((s) => {
    return (
      !studentSearch.trim() ||
      s.display_name?.toLowerCase().includes(studentSearch.toLowerCase()) ||
      s.enrollment_no?.toLowerCase().includes(studentSearch.toLowerCase()) ||
      s.application_id?.toLowerCase().includes(studentSearch.toLowerCase())
    );
  });

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleExpandDivision = async (div) => {
    if (expandedDivId === div.id) {
      setExpandedDivId(null);
      return;
    }
    setExpandedDivId(div.id);
    setLoadingSubjects(true);
    try {
      const [subRes, asgRes] = await Promise.all([
        academicApi.getDivisionSubjects(div.id),
        facultyApi.getAssignments({ division_id: div.id, is_active: true }),
      ]);
      const subjects = subRes.data?.subjects || [];
      const assignments = asgRes.data?.results || asgRes.data || [];
      setDivScheme(subRes.data?.scheme || null);
      setDivSubjects(subjects);
      setDivAssignments(assignments);
      const drafts = {};
      subjects.forEach((s) => {
        const hasLab = (s.assessment_components || []).some((c) => c.component_type.indexOf('PRACTICAL') === 0);
        const theoryHolder = assignments.find(
          (a) => a.scheme_subject === s.id && a.role !== 'LAB_INSTRUCTOR' && a.is_active
        ) || assignments.find(
          (a) => (a.subject_code || '').toUpperCase() === (s.course_code || '').toUpperCase() && a.role !== 'LAB_INSTRUCTOR' && a.is_active && !a.scheme_subject
        );
        const labHolder = assignments.find(
          (a) => a.scheme_subject === s.id && a.role === 'LAB_INSTRUCTOR' && a.is_active
        ) || assignments.find(
          (a) => (a.subject_code || '').toUpperCase() === (s.course_code || '').toUpperCase() && a.role === 'LAB_INSTRUCTOR' && a.is_active && !a.scheme_subject
        );
        drafts[s.id] = {
          theory: theoryHolder ? theoryHolder.faculty : '',
          lab: labHolder ? labHolder.faculty : '',
          hasLab,
          theoryHolderId: theoryHolder ? theoryHolder.id : null,
          labHolderId: labHolder ? labHolder.id : null,
        };
      });
      setSlotDrafts(drafts);
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to load subjects for this division.');
      setExpandedDivId(null);
    } finally {
      setLoadingSubjects(false);
    }
  };

  const handleSaveSlot = async (subject, kind) => {
    const draft = slotDrafts[subject.id] || {};
    const facultyId = kind === 'lab' ? draft.lab : draft.theory;
    const holderId = kind === 'lab' ? draft.labHolderId : draft.theoryHolderId;
    const currentHolderFaculty = (() => {
      const h = divAssignments.find((a) => a.id === holderId);
      return h ? h.faculty : '';
    })();
    if (!facultyId) {
      alert('Select a teacher first.');
      return;
    }
    if (facultyId === currentHolderFaculty) return;
    const key = `${subject.id}:${kind}`;
    try {
      setSavingSlot(key);
      if (holderId) {
        await facultyApi.deactivateAssignment(holderId, 'HOD replaced subject teacher');
      }
      await facultyApi.createAssignment({
        faculty: facultyId,
        division: expandedDivId,
        scheme_subject: subject.id,
        role: kind === 'lab' ? 'LAB_INSTRUCTOR' : 'PRIMARY_FACULTY',
      });
      setAssignSuccess(`${subject.course_code} ${kind === 'lab' ? 'lab' : 'theory'} teacher saved.`);
      setTimeout(() => setAssignSuccess(null), 4000);
      const asgRes = await facultyApi.getAssignments({ division_id: expandedDivId, is_active: true });
      const assignments = asgRes.data?.results || asgRes.data || [];
      setDivAssignments(assignments);
      setSlotDrafts((prev) => {
        const next = { ...prev };
        if (next[subject.id]) {
          if (kind === 'lab') {
            next[subject.id].lab = facultyId;
            const newHolder = assignments.find((a) => a.scheme_subject === subject.id && a.role === 'LAB_INSTRUCTOR' && a.is_active);
            next[subject.id].labHolderId = newHolder ? newHolder.id : null;
          } else {
            next[subject.id].theory = facultyId;
            const newHolder = assignments.find((a) => a.scheme_subject === subject.id && a.role !== 'LAB_INSTRUCTOR' && a.is_active);
            next[subject.id].theoryHolderId = newHolder ? newHolder.id : null;
          }
        }
        return next;
      });
    } catch (err) {
      const data = err.response?.data;
      let msg = data?.detail;
      if (!msg && data && typeof data === 'object') {
        msg = Object.entries(data)
          .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(' ') : v}`)
          .join(' | ');
      }
      alert(msg || 'Failed to save teacher.');
    } finally {
      setSavingSlot(null);
    }
  };

  const handleBulkFinalize = async () => {
    if (selectedIds.length === 0 || !bulkDivId) return;
    if (!window.confirm(`Finalize ${selectedIds.length} student(s) into the selected division?`)) return;
    try {
      setBulkSaving(true);
      const res = await academicApi.assignStudents(bulkDivId, {
        student_ids: selectedIds,
        semester_id: bulkSemId || undefined,
      });
      const skipped = res.data?.skipped?.length || 0;
      const repeats = res.data?.repeated?.length || 0;
      setAssignSuccess(
        `${res.data?.detail || 'Batch finalized.'}` +
        (repeats ? ` ${repeats} repeat(s) counted.` : '') +
        (skipped ? ` ${skipped} skipped.` : '')
      );
      setSelectedIds([]);
      setBulkDivId('');
      setBulkSemId('');
      await loadDepartmentData();
      setTimeout(() => setAssignSuccess(null), 5000);
    } catch (err) {
      alert(err.response?.data?.detail || 'Bulk finalize failed.');
    } finally {
      setBulkSaving(false);
    }
  };

  const studentColumns = [
    {
      header: (
        <input
          type="checkbox"
          title="Select all"
          checked={filteredStudents.length > 0 && selectedIds.length === filteredStudents.length}
          onChange={(e) => setSelectedIds(e.target.checked ? filteredStudents.map((s) => s.id) : [])}
        />
      ),
      render: (s) => (
        <input
          type="checkbox"
          checked={selectedIds.includes(s.id)}
          onChange={() => toggleSelect(s.id)}
        />
      ),
    },
    {
      header: 'Student Name & ID',
      accessor: 'display_name',
      render: (s) => (
        <div>
          <div style={{ fontWeight: 600, color: '#0f172a' }}>{s.display_name}</div>
          <div style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace' }}>
            {s.enrollment_no || s.application_id || '—'}
          </div>
        </div>
      ),
    },
    {
      header: 'Suggested (Formula)',
      render: (s) => (
        <span style={{ fontSize: '0.8rem', color: '#334155' }}>
          {s.suggested_semester ? (
            <>Sem {s.suggested_semester} · {s.suggested_year}</>
          ) : (
            <span style={{ color: '#94a3b8' }}>—</span>
          )}
          {s.placement_finalized ? (
            <span style={{ marginLeft: '0.4rem', color: '#166534', fontWeight: 700 }}>✓</span>
          ) : (
            <span style={{ marginLeft: '0.4rem', color: '#b45309', fontWeight: 700 }}>• unconfirmed</span>
          )}
        </span>
      ),
    },
    {
      header: 'Department / Term',
      render: (s) => (
        <span style={{ fontSize: '0.8125rem' }}>
          {s.department_code || '—'} — Sem {s.semester_number || '—'}
        </span>
      ),
    },
    {
      header: 'Assigned Division',
      render: (s) => {
        if (s.division_name) {
          return (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '6px',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: '#f0fdf4',
                color: '#166534',
                border: '1px solid #bbf7d0',
              }}
            >
              Division {s.division_name}
            </span>
          );
        }
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '0.2rem 0.6rem',
              borderRadius: '6px',
              fontSize: '0.78rem',
              fontWeight: 500,
              background: '#fef3c7',
              color: '#92400e',
              border: '1px solid #fde68a',
            }}
          >
            Unassigned
          </span>
        );
      },
    },
    {
      header: 'Action',
      align: 'right',
      render: (s) => (
        <button
          className="edvana-btn edvana-btn-outline edvana-btn-sm"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          onClick={() => {
            setStudentForDivEdit(s);
            setTargetDivId(s.division_id || '');
            setEditDivModalOpen(true);
          }}
        >
          <Edit3 size={13} />
          <span>Edit Division</span>
        </button>
      ),
    },
  ];

  // Scoped variant for the selected intake card (same row UI, header scoped to intake)
  const scopedStudentColumns = studentColumns.map((col, idx) => {
    if (idx !== 0) return col;
    return {
      ...col,
      header: (
        <input
          type="checkbox"
          title="Select all in this intake"
          checked={selectedIntakeStudents.length > 0 && selectedIntakeStudents.every((s) => selectedIds.includes(s.id))}
          onChange={(e) => {
            if (e.target.checked) {
              setSelectedIds((prev) => [...new Set([...prev, ...selectedIntakeStudents.map((s) => s.id)])]);
            } else {
              const inScope = new Set(selectedIntakeStudents.map((s) => s.id));
              setSelectedIds((prev) => prev.filter((x) => !inScope.has(x)));
            }
          }}
        />
      ),
    };
  });

  const facultyColumns = [
    {
      header: 'Faculty Member',
      accessor: 'display_name',
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{row.display_name}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--edvana-text-muted)', fontFamily: 'var(--edvana-font-mono)' }}>
            {row.employee_code}
          </div>
        </div>
      ),
    },
    {
      header: 'Designation',
      accessor: 'designation_display',
    },
    {
      header: 'Official Email',
      accessor: 'official_email',
      render: (row) => <span style={{ fontSize: '0.8125rem' }}>{row.official_email}</span>,
    },
    {
      header: 'Mobile',
      accessor: 'mobile',
      render: (row) => <span style={{ fontSize: '0.8125rem' }}>{row.mobile || '—'}</span>,
    },
    {
      header: 'Status',
      render: (row) => (
        <Badge variant={row.employment_status === 'Active' || !row.employment_status ? 'success' : 'neutral'}>
          {row.employment_status || 'Active'}
        </Badge>
      ),
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <button
          className="edvana-btn edvana-btn-outline edvana-btn-sm"
          onClick={() => navigate(`/faculty/${row.id}`)}
        >
          View Profile
        </button>
      ),
    },
  ];

  const approvedEligibilities = deptEligibilities.filter((e) => e.hod_status === 'APPROVED').length;

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading department governance overview..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem' }}>
        <ErrorState
          title="Failed to Load Governance Dashboard"
          message={error}
          onRetry={loadDepartmentData}
        />
      </div>
    );
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Department Governance' },
        ]}
        title="Department Dashboard"
        subtitle="Academic Operations, Division Architecture, and Faculty Workload Governance"
        actions={
          <button
            className="edvana-btn"
            onClick={() => navigate('/eligibility')}
            style={{
              backgroundColor: 'rgba(255, 255, 255, 0.16)',
              color: '#ffffff',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '0.8125rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.45rem',
              padding: '0.5rem 1rem',
            }}
          >
            <UserCheck size={16} />
            <span>Endorse Promotions</span>
          </button>
        }
      />

      <div className="edvana-banner-overlap">
        {assignSuccess && (
          <div
            className="edvana-badge-success"
            style={{
              marginBottom: '1.5rem',
              padding: '0.875rem 1.25rem',
              borderRadius: 'var(--edvana-radius-md)',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              width: '100%',
            }}
          >
            <CheckCircle2 size={18} />
            <span>{assignSuccess}</span>
          </div>
        )}

        {/* Department Metrics KPI Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <StatCard
            label="Department Students"
            value={`${deptStudents.length} Candidates`}
            hint={hodDeptCode ? `Enrolled in ${hodDeptCode}` : 'Enrolled in this department'}
            icon={GraduationCap}
            color="var(--edvana-brand)"
            trend="Active Roll"
          />

          <StatCard
            label="Faculty Members"
            value={`${deptFaculties.length} Faculty`}
            hint="Regular & Research Cadre"
            icon={Users}
            color="var(--edvana-info)"
            trend="Staff Strength"
          />

          <StatCard
            label="Active Divisions"
            value={`${deptDivisions.length} Sections`}
            hint="B.Tech Autonomous"
            icon={Layers}
            color="var(--edvana-brand)"
            trend="Running Cohorts"
          />

          <div
            onClick={() => navigate('/eligibility')}
            style={{ cursor: 'pointer' }}
            title="Click to view & endorse candidate eligibilities"
          >
            <StatCard
              label="Promotion Endorsements"
              value={`${approvedEligibilities} / ${deptEligibilities.length}`}
              hint="Candidates verified & signed"
              icon={Award}
              color="var(--edvana-success)"
              trend="HOD Endorsed"
            />
          </div>
        </div>

        {/* FY / DSY stream switch — mirrors AdmissionImportPage */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <div
            onClick={() => { setStreamView('FY'); setSelectedIntakeKey(null); setSelectedIds([]); }}
            style={{
              border: `2px solid ${streamView === 'FY' ? '#2563eb' : '#e2e8f0'}`,
              backgroundColor: streamView === 'FY' ? '#eff6ff' : '#ffffff',
              borderRadius: '10px', padding: '1rem 1.25rem', cursor: 'pointer',
              boxShadow: streamView === 'FY' ? '0 2px 8px rgba(37,99,235,0.12)' : 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: streamView === 'FY' ? '#1e40af' : '#1e293b' }}>
                🎓 First Year (FY) Intakes
              </span>
              {streamView === 'FY' && <CheckCircle2 size={18} style={{ color: '#2563eb' }} />}
            </div>
            <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: 0 }}>
              Regular CAP entry (Sem 1). {deptStudents.filter((s) => !s.is_direct_second_year).length} student(s) in your department.
            </p>
          </div>
          <div
            onClick={() => { setStreamView('DSY'); setSelectedIntakeKey(null); setSelectedIds([]); }}
            style={{
              border: `2px solid ${streamView === 'DSY' ? '#7e22ce' : '#e2e8f0'}`,
              backgroundColor: streamView === 'DSY' ? '#faf5ff' : '#ffffff',
              borderRadius: '10px', padding: '1rem 1.25rem', cursor: 'pointer',
              boxShadow: streamView === 'DSY' ? '0 2px 8px rgba(126,34,206,0.12)' : 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem', color: streamView === 'DSY' ? '#6b21a8' : '#1e293b' }}>
                ⚡ Direct Second Year (DSY) Intakes
              </span>
              {streamView === 'DSY' && <CheckCircle2 size={18} style={{ color: '#7e22ce' }} />}
            </div>
            <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: 0 }}>
              Lateral diploma entry (Sem 3). {deptStudents.filter((s) => s.is_direct_second_year).length} student(s) in your department.
            </p>
          </div>
        </div>

        {/* Intake cards — one per AH import slice (admission year + semester). Keeps multiple imports separate. */}
        <div className="edvana-card" style={{ padding: '1.75rem 2rem', marginBottom: '1.5rem' }}>
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
              Admission Intakes / Batches ({streamView === 'DSY' ? 'DSY' : 'FY'})
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
              Intake Cards & Division Setup
            </h2>
            <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
              Each AH import stays a separate card (year + semester). Create divisions per card, finalize students, then edit individuals below.
            </p>
          </div>
          {intakeGroups.length === 0 ? (
            <p style={{ fontSize: '0.85rem', color: '#64748b' }}>
              No {streamView === 'DSY' ? 'DSY' : 'FY'} students in your department yet.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {intakeGroups.map((g) => {
                const isActive = selectedIntake?.key === g.key;
                const setupDone = g.divisions.length > 0 && g.unassigned === 0;
                const selectIntake = () => {
                  if (selectedIntakeKey === g.key) {
                    // Clicking the active card again unselects it
                    setSelectedIntakeKey(null);
                    setSelectedIds([]);
                    setBulkDivId('');
                    setExpandedDivId(null);
                    return;
                  }
                  setSelectedIntakeKey(g.key);
                  setSelectedIds([]);
                  setBulkDivId('');
                  setExpandedDivId(null);
                };
                const openCreate = (e) => {
                  e.stopPropagation();
                  setSelectedIntakeKey(g.key);
                  const semObj = semesters.find((s) => String(s.number) === String(g.semesterNumber));
                  const activeYear = academicYears.find((y) => y.is_current) || academicYears[0];
                  setConfirmingDiv(null);
                  setConfirmingIntakeKey(null);
                  setNewDivForm((prev) => ({
                    ...prev,
                    semester_id: semObj?.id || '',
                    academic_year_id: activeYear?.id || '',
                    year_label: semObj ? ({ 1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year' }[semObj.year_level] || '') : '',
                    name: String.fromCharCode(65 + g.divisions.length),
                    seat_capacity: 60,
                    class_teacher: '',
                  }));
                  setDivFormError('');
                  setCreateDivModalOpen(true);
                };
                // Confirm flow: the class already exists (auto-created at
                // import) — open the same popup prefilled so HOD reviews /
                // corrects sem, strength, teacher, then finalizes. Never
                // creates a second division.
                const openConfirm = (e) => {
                  e.stopPropagation();
                  setSelectedIntakeKey(g.key);
                  const existing = g.divisions.find((d) => (d.enrolled_count ?? 0) > 0) || g.divisions[0];
                  if (!existing) {
                    openCreate(e);
                    return;
                  }
                  const semObj = semesters.find((s) => String(s.id) === String(existing.semester))
                    || semesters.find((s) => String(s.number) === String(existing.semester_number || g.semesterNumber));
                  setConfirmingDiv(existing);
                  setConfirmingIntakeKey(g.key);
                  setNewDivForm({
                    name: existing.name || 'A',
                    semester_id: semObj?.id || existing.semester || '',
                    academic_year_id: existing.academic_year || (academicYears.find((y) => y.is_current) || academicYears[0])?.id || '',
                    scheme_id: '',
                    year_label: semObj ? ({ 1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year' }[semObj.year_level] || '') : '',
                    seat_capacity: existing.seat_capacity || 60,
                    class_teacher: existing.class_teacher || '',
                  });
                  setDivFormError('');
                  setCreateDivModalOpen(true);
                };
                // Extra divisions are only ever needed when free seats can't
                // hold the unassigned students — otherwise Confirm suffices.
                const freeSeats = g.divisions.reduce(
                  (sum, d) => sum + Math.max(0, (Number(d.seat_capacity) || 0) - (Number(d.enrolled_count) || 0)), 0
                );
                const needsExtraDivision = g.unassigned > freeSeats;
                const openManage = (e) => {
                  e.stopPropagation();
                  selectIntake();
                  setTimeout(() => document.getElementById('hod-intake-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
                };
                const studentsInDiv = (divId) =>
                  g.students.filter((s) => String(s.division_id) === String(divId));
                const unassignedStudents = g.students.filter((s) => !s.division_id);
                return (
                  <div
                    key={g.key}
                    data-intake-card={g.key}
                    onClick={selectIntake}
                    style={{
                      border: isActive ? '1.5px solid #3b82f6' : '1px solid #e2e8f0',
                      backgroundColor: '#ffffff',
                      borderRadius: '16px',
                      padding: '1.25rem 1.5rem',
                      cursor: 'pointer',
                      position: 'relative',
                      boxShadow: isActive
                        ? '0 10px 25px -4px rgba(37, 99, 235, 0.08), 0 4px 6px -2px rgba(37, 99, 235, 0.04)'
                        : '0 1px 3px rgba(0,0,0,0.03)',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    {/* Active accent strip on the left */}
                    {isActive && (
                      <div
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          width: '4px',
                          height: '100%',
                          background: 'linear-gradient(180deg, #2563eb, #38bdf8)',
                          borderTopLeftRadius: '16px',
                          borderBottomLeftRadius: '16px',
                        }}
                      />
                    )}

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
                      <div style={{ flex: '1 1 340px', minWidth: 0 }}>
                        {/* Title & Status Badges */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                          <span style={{ fontWeight: 800, fontSize: '1.05rem', color: '#0f172a' }}>
                            Batch {g.admissionYear} • {g.yearLabel} • Sem {g.semesterNumber}
                          </span>
                          <span
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              padding: '0.2rem 0.6rem',
                              borderRadius: '9999px',
                              background: streamView === 'DSY' ? '#f3e8ff' : '#dbeafe',
                              color: streamView === 'DSY' ? '#6b21a8' : '#1e40af',
                              border: `1px solid ${streamView === 'DSY' ? '#e9d5ff' : '#bfdbfe'}`,
                            }}
                          >
                            {streamView === 'DSY' ? '⚡ DSY' : '🎓 FY'}
                          </span>
                          {setupDone ? (
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 600,
                                padding: '0.15rem 0.55rem',
                                borderRadius: '9999px',
                                background: '#f0fdf4',
                                color: '#166534',
                                border: '1px solid #bbf7d0',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.25rem',
                              }}
                            >
                              <CheckCircle2 size={12} />
                              All Allocated
                            </span>
                          ) : g.unassigned > 0 ? (
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 600,
                                padding: '0.15rem 0.55rem',
                                borderRadius: '9999px',
                                background: '#fffbeb',
                                color: '#92400e',
                                border: '1px solid #fde68a',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.25rem',
                              }}
                            >
                              <AlertCircle size={12} />
                              {g.unassigned} Unassigned
                            </span>
                          ) : null}
                        </div>

                        {/* Metrics Badges */}
                        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                              fontSize: '0.78rem',
                              fontWeight: 600,
                              color: '#334155',
                              background: '#f8fafc',
                              border: '1px solid #e2e8f0',
                              borderRadius: '6px',
                              padding: '0.2rem 0.55rem',
                            }}
                          >
                            <Users size={13} style={{ color: '#64748b' }} />
                            <strong>{g.students.length}</strong> students
                          </span>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                              fontSize: '0.78rem',
                              fontWeight: 600,
                              color: '#334155',
                              background: '#f8fafc',
                              border: '1px solid #e2e8f0',
                              borderRadius: '6px',
                              padding: '0.2rem 0.55rem',
                            }}
                          >
                            <Building2 size={13} style={{ color: '#64748b' }} />
                            <strong>{g.divisions.length}</strong> {g.divisions.length === 1 ? 'division' : 'divisions'}
                          </span>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                              fontSize: '0.78rem',
                              fontWeight: 600,
                              color: g.unassigned ? '#92400e' : '#166534',
                              background: g.unassigned ? '#fef3c7' : '#f0fdf4',
                              border: `1px solid ${g.unassigned ? '#fde68a' : '#bbf7d0'}`,
                              borderRadius: '6px',
                              padding: '0.2rem 0.55rem',
                            }}
                          >
                            {g.unassigned === 0 ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                            <strong>{g.unassigned}</strong> unassigned
                          </span>
                        </div>

                        {/* Division Quick Summary Badges */}
                        {g.divisions.length > 0 ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                            {g.divisions.map((d) => (
                              <span
                                key={d.id}
                                style={{
                                  fontSize: '0.74rem',
                                  fontWeight: 600,
                                  padding: '0.25rem 0.6rem',
                                  borderRadius: '6px',
                                  background: '#f8fafc',
                                  color: '#334155',
                                  border: '1px solid #e2e8f0',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.4rem',
                                }}
                              >
                                <span style={{ fontWeight: 800, color: '#1e40af' }}>Div {d.name}</span>
                                <span style={{ color: '#cbd5e1' }}>|</span>
                                <span style={{ color: d.class_teacher_name ? '#166534' : '#64748b' }}>
                                  {d.class_teacher_name || 'No teacher'}
                                </span>
                                <span style={{ color: '#cbd5e1' }}>|</span>
                                <span style={{ color: '#64748b', fontFamily: 'monospace' }}>
                                  {d.enrolled_count ?? 0}/{d.seat_capacity}
                                </span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: '#b45309', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                            <AlertCircle size={13} />
                            No divisions yet — create one to get started.
                          </div>
                        )}
                      </div>

                      {/* Header Action Button */}
                      <div style={{ flexShrink: 0, display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        {g.divisions.length === 0 ? (
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-primary"
                            style={{ fontSize: '0.82rem', padding: '0.5rem 1rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                            onClick={openCreate}
                          >
                            <Plus size={14} />
                            <span>Create Divisions</span>
                          </button>
                        ) : confirmedMap[g.key] ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span
                              style={{
                                fontSize: '0.78rem',
                                fontWeight: 700,
                                padding: '0.45rem 0.85rem',
                                borderRadius: '9999px',
                                background: '#f0fdf4',
                                color: '#166534',
                                border: '1px solid #bbf7d0',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                              }}
                            >
                              <CheckCircle2 size={14} />
                              Confirmed
                            </span>
                            <button
                              type="button"
                              className="edvana-btn edvana-btn-outline edvana-btn-sm"
                              style={{ padding: '0.45rem 0.6rem' }}
                              onClick={openConfirm}
                              title="Edit confirmed class"
                            >
                              <Edit3 size={14} />
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-primary"
                            style={{ fontSize: '0.82rem', padding: '0.5rem 1rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}
                            onClick={openConfirm}
                            title="Review the existing class and finalize it — edits it in place, never adds a new division"
                          >
                            <CheckCircle2 size={14} />
                            <span>Confirm Class</span>
                          </button>
                        )}
                        {g.divisions.length > 0 && needsExtraDivision && (
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-outline edvana-btn-sm"
                            style={{ fontSize: '0.75rem' }}
                            onClick={openCreate}
                            title={`Only needed because ${g.unassigned} unassigned exceed ${freeSeats} free seats`}
                          >
                            <Plus size={12} />
                            <span>Add division</span>
                          </button>
                        )}
                        {setupDone && (
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-outline"
                            style={{
                              fontSize: '0.82rem',
                              padding: '0.5rem 1rem',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.4rem',
                              borderColor: '#cbd5e1',
                            }}
                            onClick={openManage}
                          >
                            <span>Manage</span>
                            <ChevronRight size={14} />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expanded in-card detail: classrooms + subject-teacher configuration */}
                    {isActive && (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          marginTop: '1.25rem',
                          borderTop: '1px solid #e2e8f0',
                          paddingTop: '1.25rem',
                        }}
                      >
                        {/* Section 1: Classrooms — who sits where */}
                        <div style={{ marginBottom: '1.25rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                              <Building2 size={16} style={{ color: '#2563eb' }} />
                              <span style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                                Classrooms & Student Rosters
                              </span>
                              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                                — who sits where
                              </span>
                            </div>
                          </div>

                          {g.divisions.length === 0 ? (
                            <div
                              style={{
                                padding: '1rem',
                                borderRadius: '8px',
                                background: '#fffbeb',
                                border: '1px solid #fef3c7',
                                color: '#b45309',
                                fontSize: '0.82rem',
                              }}
                            >
                              No classrooms yet for this intake. Use <strong>Create Divisions</strong> above to set up classes.
                            </div>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                              {g.divisions
                                .filter((d) => studentsInDiv(d.id).length > 0 || (d.enrolled_count ?? 0) > 0)
                                .map((d) => {
                                  const roster = studentsInDiv(d.id);
                                  const isExpanded = !!rosterExpandedMap[d.id];
                                  const rawQuery = rosterSearchMap[d.id] || '';
                                  const query = rawQuery.trim().toLowerCase();
                                  const filteredRoster = query
                                    ? roster.filter((s) =>
                                        `${s.display_name || ''} ${s.enrollment_no || ''} ${s.application_id || ''}`
                                          .toLowerCase()
                                          .includes(query)
                                      )
                                    : roster;
                                  const previewLimit = 8;
                                  const displayedRoster = isExpanded ? filteredRoster : roster.slice(0, previewLimit);
                                  const remainingCount = roster.length - previewLimit;

                                  return (
                                    <div
                                      key={d.id}
                                      style={{
                                        border: '1px solid #e2e8f0',
                                        borderRadius: '12px',
                                        background: '#ffffff',
                                        padding: '0.85rem 1rem',
                                        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                                      }}
                                    >
                                      {/* Division Classroom Header */}
                                      <div
                                        style={{
                                          display: 'flex',
                                          flexWrap: 'wrap',
                                          gap: '0.6rem',
                                          alignItems: 'center',
                                          justifyContent: 'space-between',
                                          marginBottom: roster.length > 0 ? '0.75rem' : '0',
                                        }}
                                      >
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', alignItems: 'center' }}>
                                          <span
                                            style={{
                                              fontWeight: 800,
                                              fontSize: '0.82rem',
                                              color: '#1e40af',
                                              background: '#dbeafe',
                                              borderRadius: '6px',
                                              padding: '0.2rem 0.55rem',
                                            }}
                                          >
                                            Div {d.name}
                                          </span>
                                          <span
                                            style={{
                                              fontFamily: 'monospace',
                                              fontSize: '0.75rem',
                                              fontWeight: 600,
                                              color: '#475569',
                                              background: '#f1f5f9',
                                              border: '1px solid #e2e8f0',
                                              borderRadius: '5px',
                                              padding: '0.15rem 0.45rem',
                                            }}
                                          >
                                            {d.class_code || `Sem${d.semester_number}-${d.name}`}
                                          </span>
                                          {d.class_teacher_name ? (
                                            <span
                                              style={{
                                                fontSize: '0.75rem',
                                                fontWeight: 600,
                                                color: '#166534',
                                                background: '#f0fdf4',
                                                border: '1px solid #bbf7d0',
                                                borderRadius: '9999px',
                                                padding: '0.15rem 0.55rem',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '0.3rem',
                                              }}
                                            >
                                              <UserCheck size={12} />
                                              {d.class_teacher_name}
                                            </span>
                                          ) : (
                                            <span
                                              style={{
                                                fontSize: '0.75rem',
                                                fontWeight: 500,
                                                color: '#92400e',
                                                background: '#fef3c7',
                                                border: '1px solid #fde68a',
                                                borderRadius: '9999px',
                                                padding: '0.15rem 0.55rem',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '0.3rem',
                                              }}
                                            >
                                              <AlertCircle size={12} />
                                              No class teacher
                                            </span>
                                          )}
                                        </div>

                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b' }}>
                                            <strong style={{ color: '#0f172a' }}>{roster.length}</strong> students · {d.enrolled_count ?? roster.length}/{d.seat_capacity} seats
                                          </span>
                                          {roster.length > 0 && (
                                            <button
                                              type="button"
                                              onClick={() => toggleRosterExpand(d.id)}
                                              style={{
                                                background: isExpanded ? '#f1f5f9' : '#eff6ff',
                                                color: isExpanded ? '#475569' : '#2563eb',
                                                border: `1px solid ${isExpanded ? '#cbd5e1' : '#bfdbfe'}`,
                                                borderRadius: '6px',
                                                padding: '0.2rem 0.55rem',
                                                fontSize: '0.72rem',
                                                fontWeight: 600,
                                                cursor: 'pointer',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                gap: '0.25rem',
                                              }}
                                            >
                                              {isExpanded ? (
                                                <>
                                                  <ChevronUp size={12} />
                                                  <span>Hide Roster</span>
                                                </>
                                              ) : (
                                                <>
                                                  <ChevronDown size={12} />
                                                  <span>View All ({roster.length})</span>
                                                </>
                                              )}
                                            </button>
                                          )}
                                        </div>
                                      </div>

                                      {/* Search Bar when expanded */}
                                      {isExpanded && roster.length > 8 && (
                                        <div style={{ marginBottom: '0.65rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                          <div style={{ position: 'relative', flex: '1', maxWidth: '320px' }}>
                                            <Search
                                              size={13}
                                              style={{
                                                position: 'absolute',
                                                left: '0.6rem',
                                                top: '50%',
                                                transform: 'translateY(-50%)',
                                                color: '#94a3b8',
                                              }}
                                            />
                                            <input
                                              type="text"
                                              placeholder={`Filter ${roster.length} students in Div ${d.name}…`}
                                              value={rawQuery}
                                              onChange={(e) =>
                                                setRosterSearchMap((prev) => ({ ...prev, [d.id]: e.target.value }))
                                              }
                                              style={{
                                                width: '100%',
                                                fontSize: '0.75rem',
                                                padding: '0.3rem 0.6rem 0.3rem 1.8rem',
                                                borderRadius: '6px',
                                                border: '1px solid #cbd5e1',
                                                outline: 'none',
                                              }}
                                            />
                                          </div>
                                          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>
                                            Showing {filteredRoster.length} of {roster.length}
                                          </span>
                                        </div>
                                      )}

                                      {/* Student Chips Container */}
                                      <div
                                        style={{
                                          display: 'flex',
                                          flexWrap: 'wrap',
                                          gap: '0.4rem',
                                          maxHeight: isExpanded ? '240px' : 'none',
                                          overflowY: isExpanded ? 'auto' : 'visible',
                                          padding: isExpanded ? '0.5rem' : '0',
                                          background: isExpanded ? '#f8fafc' : 'transparent',
                                          borderRadius: isExpanded ? '8px' : '0',
                                          border: isExpanded ? '1px solid #f1f5f9' : 'none',
                                        }}
                                      >
                                        {displayedRoster.map((s) => (
                                          <span
                                            key={s.id}
                                            title={s.enrollment_no ? `Enrollment: ${s.enrollment_no}` : (s.application_id ? `App ID: ${s.application_id}` : '')}
                                            style={{
                                              display: 'inline-flex',
                                              alignItems: 'center',
                                              gap: '0.4rem',
                                              fontSize: '0.75rem',
                                              fontWeight: 500,
                                              padding: '0.2rem 0.6rem 0.2rem 0.35rem',
                                              borderRadius: '9999px',
                                              background: '#ffffff',
                                              border: '1px solid #e2e8f0',
                                              color: '#1e293b',
                                              boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                                            }}
                                          >
                                            <span
                                              style={{
                                                width: '20px',
                                                height: '20px',
                                                borderRadius: '50%',
                                                background: '#eff6ff',
                                                color: '#2563eb',
                                                fontWeight: 700,
                                                fontSize: '0.62rem',
                                                display: 'inline-flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                flexShrink: 0,
                                              }}
                                            >
                                              {getInitials(s.display_name)}
                                            </span>
                                            <span style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                              {formatStudentName(s.display_name)}
                                            </span>
                                          </span>
                                        ))}

                                        {/* Clickable pill to expand if collapsed and has more */}
                                        {!isExpanded && remainingCount > 0 && (
                                          <button
                                            type="button"
                                            onClick={() => toggleRosterExpand(d.id)}
                                            style={{
                                              display: 'inline-flex',
                                              alignItems: 'center',
                                              gap: '0.3rem',
                                              fontSize: '0.73rem',
                                              fontWeight: 600,
                                              padding: '0.2rem 0.65rem',
                                              borderRadius: '9999px',
                                              background: '#eff6ff',
                                              border: '1px solid #bfdbfe',
                                              color: '#1d4ed8',
                                              cursor: 'pointer',
                                            }}
                                          >
                                            <span>+{remainingCount} more</span>
                                            <ChevronDown size={11} />
                                          </button>
                                        )}

                                        {isExpanded && filteredRoster.length === 0 && (
                                          <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontStyle: 'italic', padding: '0.4rem 0' }}>
                                            No students matched "{rawQuery}".
                                          </span>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}

                              {/* Unassigned Students Section */}
                              {unassignedStudents.length > 0 && (
                                <div
                                  style={{
                                    border: '1px solid #fed7aa',
                                    borderRadius: '10px',
                                    background: '#fffbeb',
                                    padding: '0.75rem 1rem',
                                  }}
                                >
                                  <div
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: '0.4rem',
                                      fontSize: '0.8rem',
                                      fontWeight: 700,
                                      color: '#9a3412',
                                      marginBottom: '0.5rem',
                                    }}
                                  >
                                    <AlertCircle size={15} />
                                    Unassigned — {unassignedStudents.length} student(s) with no classroom yet
                                  </div>
                                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                                    {unassignedStudents.map((s) => (
                                      <span
                                        key={s.id}
                                        style={{
                                          fontSize: '0.75rem',
                                          fontWeight: 500,
                                          padding: '0.2rem 0.55rem',
                                          borderRadius: '9999px',
                                          background: '#ffffff',
                                          border: '1px solid #fed7aa',
                                          color: '#9a3412',
                                        }}
                                      >
                                        {formatStudentName(s.display_name)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Section 2: Subject teachers — set per classroom */}
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                              <BookOpen size={16} style={{ color: '#2563eb' }} />
                              <span style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                                Subject Teachers
                              </span>
                              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                                — set per classroom
                              </span>
                            </div>
                          </div>

                          {g.divisions.length === 0 ? (
                            <p style={{ fontSize: '0.8rem', color: '#64748b', margin: 0 }}>
                              Create a division first, then assign subject teachers here.
                            </p>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                              {g.divisions
                                .filter((d) => studentsInDiv(d.id).length > 0 || (d.enrolled_count ?? 0) > 0)
                                .map((d) => {
                                const isExpanded = expandedDivId === d.id;
                                return (
                                  <div
                                    key={d.id}
                                    style={{
                                      border: '1px solid #e2e8f0',
                                      borderRadius: '10px',
                                      background: '#ffffff',
                                      padding: '0.75rem 1rem',
                                      boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
                                    }}
                                  >
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'center', justifyContent: 'space-between' }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                                        <button
                                          type="button"
                                          title={isExpanded ? 'Collapse subject teachers' : 'Expand subject teachers'}
                                          onClick={() => toggleExpandDivision(d)}
                                          style={{
                                            background: isExpanded ? '#eff6ff' : '#f8fafc',
                                            border: '1px solid #e2e8f0',
                                            borderRadius: '6px',
                                            cursor: 'pointer',
                                            color: '#2563eb',
                                            padding: '0.25rem',
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                          }}
                                        >
                                          <ChevronRight
                                            size={14}
                                            style={{ transform: isExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}
                                          />
                                        </button>
                                        <span
                                          style={{
                                            fontWeight: 800,
                                            fontSize: '0.82rem',
                                            color: '#1e40af',
                                            background: '#dbeafe',
                                            borderRadius: '6px',
                                            padding: '0.15rem 0.55rem',
                                          }}
                                        >
                                          Div {d.name}
                                        </span>
                                        <span style={{ fontSize: '0.78rem', color: '#475569', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                                          {d.class_teacher_name ? (
                                            <>
                                              <UserCheck size={13} style={{ color: '#16a34a' }} />
                                              <span>Class Teacher: <strong style={{ color: '#0f172a' }}>{d.class_teacher_name}</strong></span>
                                            </>
                                          ) : (
                                            <>
                                              <AlertCircle size={13} style={{ color: '#d97706' }} />
                                              <span style={{ color: '#92400e' }}>No class teacher assigned</span>
                                            </>
                                          )}
                                        </span>
                                      </div>

                                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                        <button
                                          type="button"
                                          className="edvana-btn edvana-btn-outline edvana-btn-sm"
                                          style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
                                          onClick={() => { setSelectedDivision(d); setSelectedFacultyId(d.class_teacher || ''); setAssignModalOpen(true); }}
                                        >
                                          <UserCheck size={12} style={{ marginRight: '0.3rem' }} />
                                          {d.class_teacher_name ? 'Change Teacher' : 'Assign Teacher'}
                                        </button>
                                        <button
                                          type="button"
                                          className="edvana-btn edvana-btn-outline edvana-btn-sm"
                                          style={{
                                            fontSize: '0.75rem',
                                            padding: '0.3rem 0.65rem',
                                            background: isExpanded ? '#eff6ff' : '#ffffff',
                                            borderColor: isExpanded ? '#3b82f6' : '#cbd5e1',
                                            color: isExpanded ? '#1d4ed8' : '#334155',
                                          }}
                                          onClick={() => toggleExpandDivision(d)}
                                        >
                                          {isExpanded ? 'Hide Subjects' : 'Set Subjects'}
                                        </button>
                                      </div>
                                    </div>

                                    {isExpanded && (
                                      <div style={{ marginTop: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
                                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.15rem' }}>
                                          Subject Teachers
                                          {divScheme ? (
                                            <span style={{ fontWeight: 500, color: '#64748b' }}> · {divScheme.code} v{divScheme.version}</span>
                                          ) : (
                                            <span style={{ fontWeight: 500, color: '#b45309' }}> · no published scheme for this class yet</span>
                                          )}
                                        </div>
                                        <p style={{ margin: '0 0 0.6rem', fontSize: '0.75rem', color: '#64748b' }}>
                                          One teacher per subject per class (lab may differ from theory).
                                        </p>
                                        {loadingSubjects ? (
                                          <p style={{ fontSize: '0.8rem', color: '#64748b' }}>Loading subjects…</p>
                                        ) : divSubjects.length === 0 ? (
                                          <p style={{ fontSize: '0.8rem', color: '#64748b' }}>No scheme subjects for this semester yet.</p>
                                        ) : (
                                          divSubjects.map((s) => {
                                            const draft = slotDrafts[s.id] || {};
                                            return (
                                              <div
                                                key={s.id}
                                                style={{
                                                  display: 'flex',
                                                  flexWrap: 'wrap',
                                                  gap: '0.6rem',
                                                  alignItems: 'flex-end',
                                                  padding: '0.6rem 0',
                                                  borderTop: '1px solid #f1f5f9',
                                                }}
                                              >
                                                <div style={{ minWidth: '180px', flex: 1 }}>
                                                  <div style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: '0.8rem', color: '#0f172a' }}>
                                                    {s.course_code}
                                                  </div>
                                                  <div style={{ fontSize: '0.75rem', color: '#475569' }}>
                                                    {s.subject_title || s.subject_code} · {s.credits} cr
                                                  </div>
                                                </div>
                                                <div>
                                                  <label style={{ fontSize: '0.72rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '0.2rem' }}>
                                                    Theory teacher
                                                  </label>
                                                  <select
                                                    className="edvana-input"
                                                    style={{ minWidth: '160px', fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                                                    value={draft.theory || ''}
                                                    onChange={(e) =>
                                                      setSlotDrafts((prev) => ({
                                                        ...prev,
                                                        [s.id]: { ...prev[s.id], theory: e.target.value },
                                                      }))
                                                    }
                                                  >
                                                    <option value="">— Select —</option>
                                                    {deptFaculties.map((f) => (
                                                      <option key={f.id} value={f.id}>
                                                        {f.display_name} ({f.employee_code})
                                                      </option>
                                                    ))}
                                                  </select>
                                                </div>
                                                {draft.hasLab && (
                                                  <div>
                                                    <label style={{ fontSize: '0.72rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '0.2rem' }}>
                                                      Lab teacher
                                                    </label>
                                                    <select
                                                      className="edvana-input"
                                                      style={{ minWidth: '160px', fontSize: '0.8rem', padding: '0.35rem 0.5rem' }}
                                                      value={draft.lab || ''}
                                                      onChange={(e) =>
                                                        setSlotDrafts((prev) => ({
                                                          ...prev,
                                                          [s.id]: { ...prev[s.id], lab: e.target.value },
                                                        }))
                                                      }
                                                    >
                                                      <option value="">— Select —</option>
                                                      {deptFaculties.map((f) => (
                                                        <option key={f.id} value={f.id}>
                                                          {f.display_name} ({f.employee_code})
                                                        </option>
                                                      ))}
                                                    </select>
                                                  </div>
                                                )}
                                                <div style={{ display: 'flex', gap: '0.4rem' }}>
                                                  <button
                                                    className="edvana-btn edvana-btn-primary"
                                                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.7rem' }}
                                                    disabled={savingSlot === `${s.id}:theory`}
                                                    onClick={() => handleSaveSlot(s, 'theory')}
                                                  >
                                                    {savingSlot === `${s.id}:theory` ? 'Saving…' : 'Save Theory'}
                                                  </button>
                                                  {draft.hasLab && (
                                                    <button
                                                      className="edvana-btn edvana-btn-secondary"
                                                      style={{ fontSize: '0.75rem', padding: '0.35rem 0.7rem' }}
                                                      disabled={savingSlot === `${s.id}:lab`}
                                                      onClick={() => handleSaveSlot(s, 'lab')}
                                                    >
                                                      {savingSlot === `${s.id}:lab` ? 'Saving…' : 'Save Lab'}
                                                    </button>
                                                  )}
                                                </div>
                                              </div>
                                            );
                                          })
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected intake detail — finalized division info + scoped search/edit + per-card teacher assign */}
        {selectedIntake && (
          <div id="hod-intake-detail" className="edvana-card" style={{ padding: '1.75rem 2rem', marginBottom: '1.5rem' }}>
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
                Selected Intake
              </div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                {selectedIntake.admissionYear} • {selectedIntake.yearLabel} • Sem {selectedIntake.semesterNumber} ({selectedIntake.students.length} students)
              </h2>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
                Finalized divisions for this card are shown first. Use search below to change an individual's class, and assign/change the class teacher per division.
              </p>
            </div>
            {selectedIntake.divisions.length === 0 ? (
              <p style={{ fontSize: '0.85rem', color: '#b45309' }}>No divisions finalized for this intake yet. Use Create Divisions on the card above.</p>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', marginBottom: '1rem' }}>
                {selectedIntake.divisions.map((d) => (
                  <span key={d.id} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.4rem 0.7rem', borderRadius: '8px', background: '#f8fafc', border: '1px solid #e2e8f0', fontSize: '0.8rem' }}>
                    <button
                      type="button"
                      title={expandedDivId === d.id ? 'Collapse subject teachers' : 'Expand subject teachers'}
                      onClick={() => toggleExpandDivision(d)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1d4ed8', padding: '0.15rem', display: 'inline-flex' }}
                    >
                      <ChevronRight size={14} style={{ transform: expandedDivId === d.id ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                    </button>
                    <strong>Div {d.name}</strong>
                    <span style={{ color: '#64748b' }}>{d.class_code || `Sem${d.semester_number}-${d.name}`} • {d.enrolled_count ?? 0}/{d.seat_capacity}</span>
                    <button
                      type="button"
                      className="edvana-btn edvana-btn-outline edvana-btn-sm"
                      onClick={() => { setSelectedDivision(d); setSelectedFacultyId(d.class_teacher || ''); setAssignModalOpen(true); }}
                    >
                      {d.class_teacher_name ? 'Change Teacher' : 'Assign Teacher'}
                    </button>
                    {(d.enrolled_count ?? 0) === 0 && (
                      <button
                        title="Delete this empty division"
                        onClick={() => handleDeleteDivision(d)}
                        disabled={deletingDivId === d.id}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: '0.3rem',
                          cursor: deletingDivId === d.id ? 'default' : 'pointer',
                          color: '#b91c1c',
                          display: 'inline-flex',
                          alignItems: 'center',
                          opacity: deletingDivId === d.id ? 0.4 : 1,
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </span>
                ))}
              </div>
            )}
            {expandedDivId && selectedIntake.divisions.some((d) => d.id === expandedDivId) && (
              <div style={{ marginBottom: '1rem', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1rem 1.25rem', background: '#f8fafc' }}>
                <h3 style={{ margin: '0 0 0.25rem', fontSize: '1rem', fontWeight: 700, color: '#0f172a' }}>
                  Subject Teachers
                  {divScheme ? (
                    <span style={{ fontWeight: 500, color: '#64748b', fontSize: '0.85rem' }}>
                      {' '}· {divScheme.code} v{divScheme.version}
                    </span>
                  ) : (
                    <span style={{ fontWeight: 500, color: '#b45309', fontSize: '0.85rem' }}>
                      {' '}· no published scheme for this class yet
                    </span>
                  )}
                </h3>
                <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: '#64748b' }}>
                  One teacher per subject per class (lab may differ from theory). A teacher takes at most one subject in this class.
                </p>
                {loadingSubjects ? (
                  <p style={{ fontSize: '0.85rem', color: '#64748b' }}>Loading subjects…</p>
                ) : divSubjects.length === 0 ? (
                  <p style={{ fontSize: '0.85rem', color: '#64748b' }}>No scheme subjects for this semester yet.</p>
                ) : (
                  divSubjects.map((s) => {
                    const draft = slotDrafts[s.id] || {};
                    return (
                      <div key={s.id} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end', padding: '0.75rem 0', borderTop: '1px solid #e2e8f0' }}>
                        <div style={{ minWidth: '200px', flex: 1 }}>
                          <div style={{ fontWeight: 600, fontFamily: 'monospace' }}>{s.course_code}</div>
                          <div style={{ fontSize: '0.8rem', color: '#475569' }}>{s.subject_title || s.subject_code} · {s.credits} cr</div>
                        </div>
                        <div>
                          <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>Theory teacher</label>
                          <select
                            className="edvana-input"
                            style={{ minWidth: '180px', fontSize: '0.8125rem' }}
                            value={draft.theory || ''}
                            onChange={(e) => setSlotDrafts((prev) => ({ ...prev, [s.id]: { ...prev[s.id], theory: e.target.value } }))}
                          >
                            <option value="">— Select —</option>
                            {deptFaculties.map((f) => (
                              <option key={f.id} value={f.id}>{f.display_name} ({f.employee_code})</option>
                            ))}
                          </select>
                        </div>
                        {draft.hasLab && (
                          <div>
                            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569' }}>Lab teacher</label>
                            <select
                              className="edvana-input"
                              style={{ minWidth: '180px', fontSize: '0.8125rem' }}
                              value={draft.lab || ''}
                              onChange={(e) => setSlotDrafts((prev) => ({ ...prev, [s.id]: { ...prev[s.id], lab: e.target.value } }))}
                            >
                              <option value="">— Select —</option>
                              {deptFaculties.map((f) => (
                                <option key={f.id} value={f.id}>{f.display_name} ({f.employee_code})</option>
                              ))}
                            </select>
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button
                            className="edvana-btn edvana-btn-primary"
                            style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                            disabled={savingSlot === `${s.id}:theory`}
                            onClick={() => handleSaveSlot(s, 'theory')}
                          >
                            {savingSlot === `${s.id}:theory` ? 'Saving…' : 'Save Theory'}
                          </button>
                          {draft.hasLab && (
                            <button
                              className="edvana-btn edvana-btn-secondary"
                              style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                              disabled={savingSlot === `${s.id}:lab`}
                              onClick={() => handleSaveSlot(s, 'lab')}
                            >
                              {savingSlot === `${s.id}:lab` ? 'Saving…' : 'Save Lab'}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem', alignItems: 'center' }}>
              <div style={{ position: 'relative', minWidth: '220px' }}>
                <Search size={15} style={{ position: 'absolute', left: '0.65rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                <input
                  type="text"
                  className="edvana-input"
                  style={{ paddingLeft: '2rem', width: '100%', fontSize: '0.8125rem' }}
                  placeholder="Search this intake: name, enrollment..."
                  value={studentSearch}
                  onChange={(e) => setStudentSearch(e.target.value)}
                />
              </div>
              <span style={{ fontSize: '0.8125rem', color: '#64748b', marginLeft: 'auto' }}>
                Showing {selectedIntakeStudents.length} of {selectedIntake.students.length} in this intake
              </span>
            </div>
            {/* Bulk finalize bar (scoped to this intake's divisions) */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem', alignItems: 'center', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '0.75rem 1rem' }}>
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#0f172a' }}>
                {selectedIds.length} selected
              </span>
              <select
                className="edvana-input"
                style={{ minWidth: '170px', fontSize: '0.8125rem' }}
                value={bulkDivId}
                onChange={(e) => setBulkDivId(e.target.value)}
              >
                <option value="">Target division…</option>
                {selectedIntake.divisions.map((d) => (
                  <option key={d.id} value={d.id}>
                    Division {d.name} (Sem {d.semester_number || '—'})
                  </option>
                ))}
              </select>
              <select
                className="edvana-input"
                style={{ minWidth: '150px', fontSize: '0.8125rem' }}
                value={bulkSemId}
                onChange={(e) => setBulkSemId(e.target.value)}
              >
                <option value="">Keep semester</option>
                {semesters.map((sem) => (
                  <option key={sem.id} value={sem.id}>
                    Semester {sem.number}
                  </option>
                ))}
              </select>
              <button
                className="edvana-btn edvana-btn-primary"
                style={{ fontSize: '0.8125rem' }}
                disabled={selectedIds.length === 0 || !bulkDivId || bulkSaving}
                onClick={handleBulkFinalize}
              >
                {bulkSaving ? 'Finalizing…' : 'Finalize Selected'}
              </button>
            </div>
            <DataTable columns={scopedStudentColumns} data={selectedIntakeStudents} keyField="id" emptyMessage="No students in this intake match the search." />
          </div>
        )}

        {/* Faculty Register Table */}
        <div className="edvana-card" style={{ padding: '1.75rem 2rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
              Department Cadre / Teaching Roster
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
              Faculty Workload & Academic Register
            </h2>
            <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
              Live department register of instructional assignments, designations, and contact profiles.
            </p>
          </div>
          <DataTable
            columns={facultyColumns}
            data={deptFaculties}
            keyField="id"
            emptyMessage="No faculty records available."
          />
        </div>
      </div>

      {/* Assign Teacher Modal */}
      <Modal
        isOpen={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title={`Assign Class Teacher — Division ${selectedDivision?.name || ''}`}
        footer={
          <>
            <button
              type="button"
              className="edvana-btn edvana-btn-outline"
              onClick={() => setAssignModalOpen(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              form="assign-teacher-form"
              className="edvana-btn edvana-btn-primary"
            >
              Assign Mentor
            </button>
          </>
        }
      >
        <form id="assign-teacher-form" onSubmit={handleAssignTeacher}>
          <FormField
            label="Select Department Faculty Member"
            required
            id="faculty-select"
            help="Designated class teacher will have marksheet endorsement authority."
          >
            <select
              id="faculty-select"
              className="edvana-select"
              value={selectedFacultyId}
              onChange={(e) => setSelectedFacultyId(e.target.value)}
              required
            >
              <option value="">Choose professor or instructor...</option>
              {deptFaculties.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.display_name} ({f.designation_display})
                </option>
              ))}
            </select>
          </FormField>
        </form>
      </Modal>

      {/* Create / Confirm Class Modal — screenshot-style (same popup, Confirm edits in place) */}
      <Modal
        isOpen={createDivModalOpen}
        onClose={() => { setCreateDivModalOpen(false); setConfirmingDiv(null); setConfirmingIntakeKey(null); }}
        title={confirmingDiv ? 'Confirm Class / Division' : 'Create Class / Division'}
        footer={
          <>
            <button
              type="button"
              className="edvana-btn edvana-btn-outline"
              onClick={() => { setCreateDivModalOpen(false); setConfirmingDiv(null); setConfirmingIntakeKey(null); }}
              disabled={creatingDiv}
            >
              Cancel
            </button>
            <button
              type="submit"
              form="create-division-form"
              className="edvana-btn edvana-btn-primary"
              disabled={creatingDiv}
            >
              {creatingDiv ? (confirmingDiv ? 'Confirming...' : 'Creating...') : (confirmingDiv ? 'Confirm Class / Division' : 'Create Class / Division')}
            </button>
          </>
        }
      >
        <form id="create-division-form" onSubmit={handleCreateDivision}>
          <p style={{ fontSize: '0.8rem', color: '#64748b', margin: '0 0 1rem' }}>
            {confirmingDiv
              ? `Confirm the auto-created Division ${confirmingDiv.name} for this intake — correct semester, strength or teacher, then finalize. No new division will be created.`
              : 'Create a new class and division for your department'}
          </p>
          {divFormError && (
            <div
              style={{
                padding: '0.75rem 1rem',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                fontSize: '0.8rem',
                color: '#991b1b',
                marginBottom: '1rem',
              }}
            >
              {divFormError}
            </div>
          )}
          {(() => {
            const semObj = semesters.find((s) => String(s.id) === String(newDivForm.semester_id));
            const yearObj = academicYears.find((y) => String(y.id) === String(newDivForm.academic_year_id));
            const schemeObj = schemes.find((s) => String(s.id) === String(newDivForm.scheme_id));
            const yLabel = newDivForm.year_label || (semObj ? ({ 1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year' }[semObj.year_level] || '') : '');
            const semNum = semObj?.number || '—';
            const divName = (newDivForm.name || 'A').trim().toUpperCase() || 'A';
            const friendlyCode = `${yLabel || 'SY'}-${semNum}-${divName}`;
            const filteredSems = newDivForm.year_label
              ? semesters.filter((s) => ({ FY: 1, SY: 2, TY: 3, 'Final Year': 4 }[newDivForm.year_label] === s.year_level))
              : semesters;
            return (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem' }}>
                  <FormField label="Academic Year" required>
                    <select
                      className="edvana-select"
                      value={newDivForm.academic_year_id}
                      onChange={(e) => setNewDivForm({ ...newDivForm, academic_year_id: e.target.value })}
                      required
                    >
                      <option value="">Select year...</option>
                      {academicYears.map((y) => (
                        <option key={y.id} value={y.id}>
                          {y.code}{y.is_current ? ' (Active)' : ''}
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="Scheme" help="Display aid — resolved automatically per CONTEXT Sec 9; not stored on Division.">
                    <select
                      className="edvana-select"
                      value={newDivForm.scheme_id}
                      onChange={(e) => setNewDivForm({ ...newDivForm, scheme_id: e.target.value })}
                    >
                      <option value="">Auto (applicable scheme)</option>
                      {schemes.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.code}-v{s.version} ({s.status || 'scheme'})
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="Year" required>
                    <select
                      className="edvana-select"
                      value={newDivForm.year_label}
                      onChange={(e) => setNewDivForm({ ...newDivForm, year_label: e.target.value, semester_id: '' })}
                      required
                    >
                      <option value="">Select year...</option>
                      <option value="FY">First Year (FY)</option>
                      <option value="SY">Second Year (SY)</option>
                      <option value="TY">Third Year (TY)</option>
                      <option value="Final Year">Final Year</option>
                    </select>
                  </FormField>
                  <FormField label="Semester" required>
                    <select
                      className="edvana-select"
                      value={newDivForm.semester_id}
                      onChange={(e) => setNewDivForm({ ...newDivForm, semester_id: e.target.value })}
                      required
                    >
                      <option value="">Select semester...</option>
                      {filteredSems.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.number} ({s.term_type === 'EVEN' ? 'Even' : 'Odd'})
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="Division" required help="e.g. A, B, C">
                    <input
                      type="text"
                      className="edvana-input"
                      style={{ width: '100%' }}
                      placeholder="A"
                      maxLength={5}
                      value={newDivForm.name}
                      onChange={(e) => setNewDivForm({ ...newDivForm, name: e.target.value.toUpperCase() })}
                      required
                    />
                  </FormField>
                  <FormField label="Class Code (Optional)" help="Auto-generated if left blank">
                    <input
                      type="text"
                      className="edvana-input"
                      style={{ width: '100%', background: '#f8fafc' }}
                      value={friendlyCode}
                      readOnly
                      title="Auto-generated display code (not a stored column)"
                    />
                  </FormField>
                  <FormField label="Class Teacher" required>
                    <select
                      className="edvana-select"
                      value={newDivForm.class_teacher}
                      onChange={(e) => setNewDivForm({ ...newDivForm, class_teacher: e.target.value })}
                      required
                    >
                      <option value="">Select teacher...</option>
                      {deptFaculties.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.display_name} ({f.designation_display})
                        </option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="Expected Strength (Optional)">
                    <input
                      type="number"
                      min={1}
                      max={200}
                      className="edvana-input"
                      style={{ width: '100%' }}
                      value={newDivForm.seat_capacity}
                      onChange={(e) => setNewDivForm({ ...newDivForm, seat_capacity: e.target.value })}
                    />
                  </FormField>
                </div>
                <div
                  style={{
                    marginTop: '1rem',
                    padding: '0.85rem 1rem',
                    background: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    color: '#1e40af',
                    display: 'flex',
                    gap: '0.6rem',
                  }}
                >
                  <Info size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <strong>{confirmingDiv ? 'This will confirm:' : 'This will create:'}</strong>
                    <div>{yLabel || '—'} - Semester {semNum} - Division {divName} for Academic Year {yearObj?.code || '—'}{schemeObj ? ` under ${schemeObj.code} v${schemeObj.version}` : ''}</div>
                    <div style={{ color: '#3b82f6' }}>{confirmingDiv ? `Finalizes the existing Division ${confirmingDiv.name} with your corrections — no extra division. Code ${friendlyCode} is display-only.` : `Students can be assigned to this class after creation. Code ${friendlyCode} is display-only.`}</div>
                  </div>
                </div>
              </>
            );
          })()}
        </form>
      </Modal>

      {/* Edit Student Division Modal */}
      <Modal
        isOpen={editDivModalOpen}
        onClose={() => setEditDivModalOpen(false)}
        title={`Edit Student Division — ${studentForDivEdit?.display_name || ''}`}
        footer={
          <>
            <button
              type="button"
              className="edvana-btn edvana-btn-outline"
              onClick={() => setEditDivModalOpen(false)}
              disabled={savingStudentDiv}
            >
              Cancel
            </button>
            <button
              type="submit"
              form="edit-student-division-form"
              className="edvana-btn edvana-btn-primary"
              disabled={savingStudentDiv}
            >
              {savingStudentDiv ? 'Saving...' : 'Save Division Allocation'}
            </button>
          </>
        }
      >
        <form id="edit-student-division-form" onSubmit={handleSaveStudentDivision}>
          <div
            style={{
              padding: '0.85rem 1rem',
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '6px',
              fontSize: '0.8125rem',
              lineHeight: 1.6,
              marginBottom: '1.25rem',
            }}
          >
            <div><strong>Candidate:</strong> {studentForDivEdit?.display_name}</div>
            <div><strong>Enrollment:</strong> <span style={{ fontFamily: 'monospace' }}>{studentForDivEdit?.enrollment_no || '—'}</span></div>
            <div><strong>Current Semester:</strong> Semester {studentForDivEdit?.semester_number || '—'}</div>
          </div>

          <FormField label="Assigned Class Division" required>
            <select
              className="edvana-select"
              value={targetDivId}
              onChange={(e) => setTargetDivId(e.target.value)}
            >
              <option value="">-- Unassigned --</option>
              {deptDivisions
                .filter((d) => !studentForDivEdit?.semester_number || String(d.semester_number) === String(studentForDivEdit?.semester_number))
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    Division {d.name} (Semester {d.semester_number})
                  </option>
                ))}
            </select>
          </FormField>
        </form>
      </Modal>
    </>
  );
}
