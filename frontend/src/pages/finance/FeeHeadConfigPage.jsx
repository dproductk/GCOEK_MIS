import React, { useState, useEffect } from 'react';
import { 
  Coins, Plus, RefreshCw, SlidersHorizontal, Trash2, Package, 
  CheckCircle2, AlertCircle, X, Check, Calendar, ChevronDown
} from 'lucide-react';
import financeApi from '../../api/financeApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function FeeHeadConfigPage() {
  const navigate = useNavigate();
  const { user, activeRole, hasRole } = useAuth();

  const isAdministrativeHead = 
    activeRole?.codename === 'ADMIN_HEAD' || 
    activeRole?.codename === 'SYSADMIN' || 
    (typeof hasRole === 'function' && (hasRole('ADMIN_HEAD') || hasRole('SYSADMIN'))) || 
    user?.user_type === 'ADMIN';

  const isAccountant = 
    activeRole?.codename === 'ACCOUNTANT' || 
    (typeof hasRole === 'function' && hasRole('ACCOUNTANT'));

  const [feeHeads, setFeeHeads] = useState([]);
  const [academicYears, setAcademicYears] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  // Errors from this form MUST render inside the modal — the page-level
  // banner sits behind the modal overlay and would never be seen.
  const [modalError, setModalError] = useState(null);

  // Filters
  const [selectedYear, setSelectedYear] = useState('');

  // Add / Edit Modal state
  const [modalMode, setModalMode] = useState('add'); // 'add' | 'edit'
  const [showModal, setShowModal] = useState(false);
  const [editingHeadId, setEditingHeadId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    code: '',
    tag: '',
    description: '',
    academic_year: '',
    display_order: 1,
    allowed_amounts_str: '',
    fee_type: 'INSTITUTE',
    is_active: true,
  });

  // Delete modal state
  const [headToDelete, setHeadToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // ---- Fee Packages (total-amount dropdown options for the accountant) ----
  const [feePackages, setFeePackages] = useState([]);
  const [showPkgModal, setShowPkgModal] = useState(false);
  const [pkgModalMode, setPkgModalMode] = useState('add'); // 'add' | 'edit'
  const [editingPackageId, setEditingPackageId] = useState(null);
  const [pkgError, setPkgError] = useState(null);
  const [pkgSubmitting, setPkgSubmitting] = useState(false);
  // Heads loaded for the package modal's own academic year (may differ from
  // the page-level year filter when editing a package from another year).
  const [pkgHeads, setPkgHeads] = useState([]);
  const [pkgHeadsLoading, setPkgHeadsLoading] = useState(false);
  const [pkgData, setPkgData] = useState({
    name: '',
    academic_year: '',
    is_active: true,
    items: [], // [{ head, amount }]
  });
  const [packageToDelete, setPackageToDelete] = useState(null);
  const [pkgDeleting, setPkgDeleting] = useState(false);

  // Resilient data fetching
  const fetchData = async (isManualRefresh = false) => {
    if (isManualRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      // Fetch fee heads, academic years, and fee packages concurrently.
      const [headsResult, yearsResult, packagesResult] = await Promise.allSettled([
        financeApi.getFeeHeads({ 
          academic_year_id: selectedYear || undefined,
        }),
        academicApi.getAcademicYears(),
        financeApi.getFeePackages({
          academic_year_id: selectedYear || undefined,
        }),
      ]);

      // 1. Process Academic Years (backend only — never invented).
      let years = [];
      if (yearsResult.status === 'fulfilled') {
        const rawYears = yearsResult.value.data?.results || yearsResult.value.data || [];
        years = Array.isArray(rawYears) ? rawYears : [];
      } else {
        setError('Could not load academic years. Fee-head configuration needs them — please retry.');
      }
      setAcademicYears(years);

      // 2. Process Fee Heads
      if (headsResult.status === 'fulfilled') {
        const rawHeads = headsResult.value.data?.results || headsResult.value.data || [];
        const sorted = [...rawHeads].sort((a, b) => (a.display_order || 99) - (b.display_order || 99));
        setFeeHeads(sorted);
      } else {
        console.error('Error fetching fee heads:', headsResult.reason);
        setError('Failed to fetch fee heads configuration.');
      }

      // 3. Process Fee Packages (non-fatal: the heads grid must still render
      //    even if the packages endpoint hiccups).
      if (packagesResult.status === 'fulfilled') {
        const rawPkgs = packagesResult.value.data?.results || packagesResult.value.data || [];
        setFeePackages(Array.isArray(rawPkgs) ? rawPkgs : []);
      } else {
        console.error('Error fetching fee packages:', packagesResult.reason);
      }
    } catch (err) {
      console.error('Unexpected error loading fee configuration:', err);
      setError('Unexpected error loading configuration data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedYear]);

  // Open modal for Adding
  const handleOpenAdd = () => {
    const nextOrder = feeHeads.length > 0 ? Math.max(...feeHeads.map(h => h.display_order || 0)) + 1 : 1;
    const defaultYear = selectedYear || academicYears.find(y => y.is_current)?.id || academicYears[0]?.id || '';
    
    setModalMode('add');
    setEditingHeadId(null);
    setModalError(null);
    setFormData({
      name: '',
      code: '',
      codeTouched: false,
      tag: '',
      description: '',
      academic_year: defaultYear,
      display_order: nextOrder,
      allowed_amounts_str: '',
      fee_type: 'INSTITUTE',
      is_active: true,
    });
    setShowModal(true);
  };

  // Open modal for Configuring / Editing
  const handleOpenConfigure = (head) => {
    setModalMode('edit');
    setEditingHeadId(head.id);
    setModalError(null);
    const amountsList = Array.isArray(head.allowed_amounts) && head.allowed_amounts.length > 0
      ? head.allowed_amounts
      : (head.amount ? [parseFloat(head.amount)] : []);

    setFormData({
      name: head.name || '',
      code: head.code || '',
      codeTouched: true, // editing an existing head: never silently rewrite its code
      tag: head.tag || '',
      description: head.description || '',
      academic_year: head.academic_year || '',
      display_order: head.display_order || 1,
      allowed_amounts_str: amountsList.join(', '),
      fee_type: head.fee_type || 'INSTITUTE',
      is_active: head.is_active !== undefined ? head.is_active : true,
    });
    setShowModal(true);
  };

  // Submit Add or Edit
  const handleSubmit = async (e) => {
    e.preventDefault();
    setModalError(null);

    // No invented values: every business fact is required from the user.
    if (!formData.name.trim()) {
      setModalError('Fee head name is required.');
      return;
    }
    if (!formData.code.trim()) {
      setModalError('Fee head code is required (e.g. TF).');
      return;
    }
    if (!formData.academic_year || !academicYears.some(y => String(y.id) === String(formData.academic_year))) {
      setModalError('Select a valid academic year from the configured list.');
      return;
    }
    setSubmitting(true);

    // Parse allowed amounts
    const parsedAmounts = formData.allowed_amounts_str
      .split(',')
      .map(s => s.trim().replace(/[^\d.-]/g, ''))
      .filter(s => s !== '')
      .map(s => parseFloat(s))
      .filter(n => !isNaN(n));

    // Ensure sorted ascending and unique
    const uniqueAmounts = Array.from(new Set(parsedAmounts)).sort((a, b) => a - b);
    if (uniqueAmounts.length === 0) {
      setModalError('Enter at least one allowed amount (comma separated).');
      setSubmitting(false);
      return;
    }
    const maxAmount = Math.max(...uniqueAmounts);

    const payload = {
      name: formData.name.trim(),
      code: formData.code.trim().toUpperCase(),
      tag: (formData.tag || formData.code).trim().toUpperCase(),
      description: formData.description.trim(),
      display_order: parseInt(formData.display_order, 10) || 1,
      allowed_amounts: uniqueAmounts,
      amount: maxAmount,
      academic_year: formData.academic_year,
      fee_type: formData.fee_type || 'INSTITUTE',
      is_active: formData.is_active,
    };

    try {
      if (modalMode === 'add') {
        await financeApi.createFeeHead(payload);
        setSuccessMsg(`Fee head "${payload.name}" created successfully!`);
      } else {
        await financeApi.updateFeeHead(editingHeadId, payload);
        setSuccessMsg(`Fee head "${payload.name}" updated successfully!`);
      }
      setShowModal(false);
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3500);
    } catch (err) {
      console.error('Error saving fee head:', err);
      const data = err.response?.data;
      let detail;
      if (typeof data?.detail === 'string') {
        detail = data.detail;
      } else if (data && typeof data === 'object') {
        // Flatten DRF field errors, e.g. { code: ["fee head with this code already exists."] }
        detail = Object.entries(data)
          .map(([key, value]) => {
            const keyLabel = key.replace(/_/g, ' ');
            const text = Array.isArray(value) ? value.join(' ') : String(value);
            // Skip the numeric index wrapper of non-field errors
            return key === 'non_field_errors' ? text : `${keyLabel}: ${text}`;
          })
          .join(' — ');
      }
      setModalError(detail || 'Failed to save fee head.');
    } finally {
      setSubmitting(false);
    }
  };

  // Confirm delete
  const handleDeleteConfirm = async () => {
    if (!headToDelete) return;
    setDeleting(true);
    setError(null);
    try {
      await financeApi.deleteFeeHead(headToDelete.id);
      setSuccessMsg(`Fee head "${headToDelete.name}" removed successfully.`);
      setHeadToDelete(null);
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3500);
    } catch (err) {
      console.error('Error deleting fee head:', err);
      setError(err.response?.data?.detail || 'Failed to delete fee head. It may be linked to existing payment records.');
    } finally {
      setDeleting(false);
    }
  };

  // Helper to format currency values cleanly
  const formatAmount = (num) => {
    const val = Number(num);
    if (isNaN(val)) return '₹0';
    return `₹${val.toLocaleString('en-IN')}`;
  };

  // ---- Fee Package handlers ----

  // Load active heads of a given year for the package modal (fresh fetch —
  // the page grid may be filtered to a different year).
  const loadPkgHeads = async (yearId) => {
    if (!yearId || !academicYears.some(y => String(y.id) === String(yearId))) {
      setPkgHeads([]);
      return;
    }
    setPkgHeadsLoading(true);
    try {
      const res = await financeApi.getFeeHeads({ academic_year_id: yearId });
      const raw = res?.data?.results || res?.data || [];
      const sorted = (Array.isArray(raw) ? raw : [])
        .filter(h => h.is_active)
        .sort((a, b) => (a.display_order || 99) - (b.display_order || 99));
      setPkgHeads(sorted);
    } catch (err) {
      console.error('Error loading heads for package modal:', err);
      setPkgHeads([]);
      setPkgError('Could not load fee heads for the selected academic year.');
    } finally {
      setPkgHeadsLoading(false);
    }
  };

  const handleOpenPackageAdd = () => {
    const yearId = selectedYear || academicYears.find(y => y.is_current)?.id || academicYears[0]?.id || '';
    const nextOrder = feePackages.length > 0
      ? Math.max(...feePackages.map(p => p.display_order || 0)) + 1
      : 1;
    setPkgModalMode('add');
    setEditingPackageId(null);
    setPkgError(null);
    setPkgData({
      name: '',
      academic_year: yearId,
      is_active: true,
      items: [],
      _order: nextOrder,
    });
    setShowPkgModal(true);
    loadPkgHeads(yearId);
  };

  const handleOpenPackageEdit = (pkg) => {
    setPkgModalMode('edit');
    setEditingPackageId(pkg.id);
    setPkgError(null);
    const resolved = Array.isArray(pkg.items_resolved) ? pkg.items_resolved : [];
    setPkgData({
      name: pkg.name || '',
      academic_year: String(pkg.academic_year || ''),
      is_active: pkg.is_active !== undefined ? pkg.is_active : true,
      items: resolved.map(it => ({ head: it.head, amount: it.amount })),
      _order: pkg.display_order || 1,
    });
    setShowPkgModal(true);
    loadPkgHeads(String(pkg.academic_year || ''));
  };

  const handlePkgItemChange = (index, field, value) => {
    setPkgData(prev => {
      const items = prev.items.map((item, i) => {
        if (i !== index) return item;
        if (field === 'head') {
          // New head selected: preselect its cheapest preset so the row is
          // never left with an amount that head disallows.
          const head = pkgHeads.find(h => String(h.id) === String(value));
          const allowed = Array.isArray(head?.allowed_amounts) ? head.allowed_amounts : [];
          return { head: value, amount: allowed.length > 0 ? Number(allowed[0]) : (item.amount || 0) };
        }
        return { ...item, amount: parseFloat(value) || 0 };
      });
      return { ...prev, items };
    });
  };

  const handlePkgAddRow = () => {
    setPkgData(prev => ({
      ...prev,
      items: [...(prev.items || []), { head: '', amount: 0 }],
    }));
  };

  const handlePkgRemoveRow = (index) => {
    setPkgData(prev => ({ ...prev, items: prev.items.filter((_, i) => i !== index) }));
  };

  const handlePkgYearChange = (yearId) => {
    setPkgData(prev => ({ ...prev, academic_year: yearId, items: [] }));
    loadPkgHeads(yearId);
  };

  // Live total of what the accountant's dropdown will show for this package
  const pkgLiveTotal = (pkgData.items || []).reduce(
    (acc, it) => acc + (parseFloat(it.amount) || 0), 0
  );

  const handlePackageSubmit = async (e) => {
    e.preventDefault();
    setPkgError(null);

    if (!pkgData.name.trim()) {
      setPkgError('Package name is required.');
      return;
    }
    if (!pkgData.academic_year || !academicYears.some(y => String(y.id) === String(pkgData.academic_year))) {
      setPkgError('Select a valid academic year from the configured list.');
      return;
    }
    const validItems = (pkgData.items || []).filter(it => it.head && (parseFloat(it.amount) || 0) >= 0);
    if (validItems.length === 0) {
      setPkgError('Add at least one fee head row with an amount (a package cannot be empty).');
      return;
    }
    if (pkgData.items.some(it => !it.head)) {
      setPkgError('Every row needs a fee head selected (remove empty rows first).');
      return;
    }
    setPkgSubmitting(true);

    const payload = {
      name: pkgData.name.trim(),
      academic_year: pkgData.academic_year,
      items: validItems.map(it => ({
        head: it.head,
        amount: parseFloat(it.amount) || 0,
      })),
      display_order: parseInt(pkgData._order, 10) || 1,
      is_active: pkgData.is_active,
    };

    try {
      if (pkgModalMode === 'add') {
        await financeApi.createFeePackage(payload);
        setSuccessMsg(`Fee package "${payload.name}" created successfully!`);
      } else {
        await financeApi.updateFeePackage(editingPackageId, payload);
        setSuccessMsg(`Fee package "${payload.name}" updated successfully!`);
      }
      setShowPkgModal(false);
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3500);
    } catch (err) {
      console.error('Error saving fee package:', err);
      const data = err.response?.data;
      let detail;
      if (typeof data?.detail === 'string') {
        detail = data.detail;
      } else if (data && typeof data === 'object') {
        detail = Object.entries(data)
          .map(([key, value]) => {
            const keyLabel = key.replace(/_/g, ' ');
            const text = Array.isArray(value) ? value.join(' ') : String(value);
            return key === 'non_field_errors' ? text : `${keyLabel}: ${text}`;
          })
          .join(' — ');
      }
      setPkgError(detail || 'Failed to save fee package.');
    } finally {
      setPkgSubmitting(false);
    }
  };

  const handlePackageDeleteConfirm = async () => {
    if (!packageToDelete) return;
    setPkgDeleting(true);
    setError(null);
    try {
      await financeApi.deleteFeePackage(packageToDelete.id);
      setSuccessMsg(`Fee package "${packageToDelete.name}" removed successfully.`);
      setPackageToDelete(null);
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3500);
    } catch (err) {
      console.error('Error deleting fee package:', err);
      setError(err.response?.data?.detail || 'Failed to delete fee package.');
    } finally {
      setPkgDeleting(false);
    }
  };

  // Extract allowed amounts list with safe fallback
  const getCardAmounts = (head) => {
    if (Array.isArray(head.allowed_amounts) && head.allowed_amounts.length > 0) {
      return head.allowed_amounts;
    }
    if (head.amount && parseFloat(head.amount) > 0) {
      return [0, parseFloat(head.amount)];
    }
    return [0];
  };

  // If logged in as Accountant, restrict fee head configuration to Administrative Head only
  if (isAccountant && !isAdministrativeHead) {
    return (
      <>
        <PageHeader
          breadcrumbs={[
            { label: 'Home', to: '/dashboard' },
            { label: 'Finance' },
            { label: 'Fee Head Configuration' },
          ]}
          title="Fee Head Configuration"
          subtitle="Institutional fee structure configuration is restricted."
        />
        <div className="edvana-banner-overlap" style={{ maxWidth: '800px', margin: '0 auto', paddingBottom: '3rem' }}>
          <div className="edvana-card" style={{ padding: '3.5rem 2rem', textAlign: 'center' }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: '#eff6ff',
              color: '#1E60DC',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.25rem auto'
            }}>
              <Coins size={28} />
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
              Administrative Head Access Only
            </h2>
            <p style={{ color: '#64748b', fontSize: '0.875rem', maxWidth: '520px', margin: '0 auto 1.5rem auto', lineHeight: 1.6 }}>
              Fee Head Configuration can only be set and managed by the <strong>Administrative Head</strong>. 
              As an Accountant, your desk allows you to verify candidate admissions, set eligible fees, and record payment collections at the Candidate Fee Desk.
            </p>
            <button
              type="button"
              onClick={() => navigate('/finance/fee-desk')}
              style={{
                background: '#1E60DC',
                color: '#ffffff',
                border: 'none',
                borderRadius: '20px',
                padding: '0.5rem 1.6rem',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 1px 3px rgba(58, 129, 246, 0.25)',
                transition: 'background 0.15s ease'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#1E60DC'}
            >
              Go to Candidate Fee Desk
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
        ]}
        title="Dashboard"
        subtitle="Welcome to your student portal"
        badge={true}
      />

      <div className="edvana-banner-overlap" style={{ maxWidth: '1280px', margin: '0 auto', paddingBottom: '3rem' }}>
        {successMsg && (
          <div style={{ 
            marginBottom: '1.5rem', 
            padding: '1rem 1.5rem', 
            background: '#f0fdf4', 
            border: '1px solid #bbf7d0', 
            borderRadius: '12px', 
            color: '#166534', 
            fontSize: '0.875rem', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.75rem',
            boxShadow: '0 2px 6px rgba(22, 101, 52, 0.06)'
          }}>
            <CheckCircle2 size={20} style={{ flexShrink: 0, color: '#16a34a' }} />
            <div style={{ fontWeight: 600 }}>{successMsg}</div>
          </div>
        )}

        {error && (
          <div style={{ 
            marginBottom: '1.5rem', 
            padding: '1rem 1.5rem', 
            background: '#fef2f2', 
            border: '1px solid #fecaca', 
            borderRadius: '12px', 
            color: '#991b1b', 
            fontSize: '0.875rem', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.75rem',
            boxShadow: '0 2px 6px rgba(153, 27, 27, 0.06)'
          }}>
            <AlertCircle size={20} style={{ flexShrink: 0, color: '#dc2626' }} />
            <div style={{ fontWeight: 600 }}>{error}</div>
          </div>
        )}

        {/* Top Header Card */}
        <div style={{
          background: '#ffffff',
          borderRadius: '18px',
          border: '1px solid #e2e8f0',
          padding: '1.75rem 2rem',
          boxShadow: '0 4px 18px -4px rgba(15, 23, 42, 0.05), 0 2px 6px -2px rgba(15, 23, 42, 0.03)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1.5rem',
          marginBottom: '2rem'
        }}>
          {/* Left: Icon, Title, Subtitle, Portal badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', minWidth: '320px', flex: 1 }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '16px',
              background: '#eff6ff',
              border: '1px solid #dbeafe',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: '0 2px 8px rgba(37, 99, 235, 0.08)'
            }}>
              <Coins size={28} style={{ color: '#2563eb' }} />
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <h1 style={{
                  fontSize: '1.45rem',
                  fontWeight: 800,
                  color: '#0f172a',
                  letterSpacing: '-0.02em',
                  margin: 0,
                  lineHeight: 1.25
                }}>
                  Fee Head Configuration
                </h1>
                <span style={{
                  fontSize: '0.675rem',
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: '#475569',
                  background: '#f8fafc',
                  border: '1px solid #cbd5e1',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '6px'
                }}>
                  ADMINISTRATIVE HEAD PORTAL
                </span>
              </div>
              <p style={{
                margin: '0.4rem 0 0 0',
                fontSize: '0.875rem',
                color: '#64748b',
                lineHeight: 1.5,
                maxWidth: '750px'
              }}>
                Government College of Engineering, Kolhapur — Configure fee heads and selectable denomination values for the Accountant fee marking desk.
              </p>
            </div>
          </div>

          {/* Right: Academic Year Filter, Refresh button, + Add Fee Head */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative' }}>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                style={{
                  height: '42px',
                  padding: '0 2.2rem 0 1rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: '#334155',
                  background: '#ffffff',
                  border: '1px solid #cbd5e1',
                  borderRadius: '10px',
                  outline: 'none',
                  cursor: 'pointer',
                  appearance: 'none',
                  minWidth: '185px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
                }}
              >
                <option value="">All Academic Years</option>
                {academicYears.map((ay) => (
                  <option key={ay.id} value={ay.id}>
                    {ay.code} {ay.is_current ? '(Current)' : ''}
                  </option>
                ))}
              </select>
              <ChevronDown 
                size={16} 
                style={{ 
                  position: 'absolute', 
                  right: '0.75rem', 
                  top: '50%', 
                  transform: 'translateY(-50%)', 
                  pointerEvents: 'none', 
                  color: '#64748b' 
                }} 
              />
            </div>

            <button
              onClick={() => fetchData(true)}
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                border: '1px solid #cbd5e1',
                background: '#ffffff',
                color: '#475569',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}
              title="Refresh Records"
            >
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            </button>

            <button
              onClick={handleOpenAdd}
              style={{
                height: '42px',
                padding: '0 1.25rem',
                borderRadius: '10px',
                background: '#2563eb',
                color: '#ffffff',
                border: 'none',
                fontWeight: 600,
                fontSize: '0.85rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(37, 99, 235, 0.3)',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#1d4ed8'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#2563eb'}
            >
              <Plus size={17} />
              <span>Add Fee Head</span>
            </button>
          </div>
        </div>

        {/* Content Body: Grid of Cards */}
        {loading ? (
          <div style={{ 
            background: '#ffffff', 
            borderRadius: '18px', 
            border: '1px solid #e2e8f0', 
            padding: '5rem 2rem',
            boxShadow: '0 4px 18px -4px rgba(15, 23, 42, 0.04)'
          }}>
            <LoadingState message="Loading configured fee heads and presets..." />
          </div>
        ) : feeHeads.length === 0 ? (
          <div style={{ 
            background: '#ffffff', 
            borderRadius: '18px', 
            border: '1px solid #e2e8f0', 
            padding: '5rem 2rem',
            boxShadow: '0 4px 18px -4px rgba(15, 23, 42, 0.04)'
          }}>
            <EmptyState
              title="No Fee Heads Configured"
              message="Get started by clicking '+ Add Fee Head' to establish selectable presets for the fee desk."
              actionLabel="Add Fee Head"
              onAction={handleOpenAdd}
            />
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: '1.75rem',
            alignItems: 'stretch'
          }}>
            {feeHeads.map((head, idx) => {
              const amounts = getCardAmounts(head);
              const tagLabel = head.tag || (head.code ? head.code.slice(0, 6) : `FH${idx + 1}`);

              return (
                <div
                  key={head.id}
                  style={{
                    background: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '18px',
                    padding: '1.6rem 1.75rem',
                    boxShadow: '0 4px 16px -2px rgba(15, 23, 42, 0.04), 0 2px 4px -2px rgba(15, 23, 42, 0.02)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    transition: 'box-shadow 0.2s ease, transform 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = '0 10px 24px -4px rgba(15, 23, 42, 0.08), 0 4px 8px -2px rgba(15, 23, 42, 0.03)';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = '0 4px 16px -2px rgba(15, 23, 42, 0.04), 0 2px 4px -2px rgba(15, 23, 42, 0.02)';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <div>
                    {/* Top Row: Tag badge + Title on left, Status badge on right */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      gap: '0.65rem',
                      marginBottom: '0.65rem'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', flex: 1, minWidth: 0 }}>
                        <span style={{
                          background: '#eff6ff',
                          color: '#2563eb',
                          border: '1px solid #dbeafe',
                          fontSize: '0.625rem',
                          fontWeight: 800,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          padding: '0.18rem 0.5rem',
                          borderRadius: '8px',
                          flexShrink: 0,
                          marginTop: '0.15rem',
                          whiteSpace: 'nowrap'
                        }}>
                          {tagLabel}
                        </span>
                        <h2 style={{
                          fontSize: '1rem',
                          fontWeight: 700,
                          color: '#0f172a',
                          margin: 0,
                          lineHeight: 1.3
                        }}>
                          {head.name}
                        </h2>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0 }}>
                        <span style={{
                          background: head.fee_type === 'GOVERNMENT' ? '#fefce8' : '#f1f5f9',
                          color: head.fee_type === 'GOVERNMENT' ? '#a16207' : '#64748b',
                          border: `1px solid ${head.fee_type === 'GOVERNMENT' ? '#fde68a' : '#e2e8f0'}`,
                          fontSize: '0.625rem',
                          fontWeight: 800,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '9999px',
                          whiteSpace: 'nowrap'
                        }}>
                          {head.fee_type === 'GOVERNMENT' ? 'GOVT' : 'INST.'}
                        </span>
                        {head.is_active ? (
                        <span style={{
                          background: '#ecfdf5',
                          color: '#15803d',
                          border: '1px solid #bbf7d0',
                          fontSize: '0.625rem',
                          fontWeight: 800,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '9999px',
                          whiteSpace: 'nowrap'
                        }}>
                          ACTIVE
                        </span>
                      ) : (
                        <span style={{
                          background: '#f1f5f9',
                          color: '#64748b',
                          border: '1px solid #e2e8f0',
                          fontSize: '0.625rem',
                          fontWeight: 800,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          padding: '0.15rem 0.5rem',
                          borderRadius: '9999px',
                          whiteSpace: 'nowrap'
                        }}>
                          INACTIVE
                        </span>
                      )}
                      </div>
                    </div>

                    {/* Subtitle / Description */}
                    <p style={{
                      fontSize: '0.85rem',
                      color: '#64748b',
                      margin: '0.5rem 0 1.35rem 0',
                      lineHeight: 1.5,
                      minHeight: '2.5rem'
                    }}>
                      {head.description || 'Institutional fee schedule preset values for candidate collection.'}
                    </p>

                    {/* Inner Grey Box: ALLOWED DROPDOWN AMOUNTS (ACCOUNTANT) */}
                    <div style={{
                      background: '#f8fafc',
                      borderRadius: '12px',
                      padding: '1rem 1.15rem',
                      marginBottom: '1.5rem',
                      border: '1px solid #e2e8f0'
                    }}>
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '0.75rem'
                      }}>
                        <span style={{
                          fontSize: '0.6875rem',
                          fontWeight: 800,
                          letterSpacing: '0.06em',
                          color: '#64748b',
                          textTransform: 'uppercase',
                        }}>
                          ALLOWED DROPDOWN AMOUNTS (ACCOUNTANT)
                        </span>
                        <span style={{
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          color: '#2563eb',
                        }}>
                          {amounts.length} Presets
                        </span>
                      </div>

                      {/* Amounts Pills */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {amounts.map((amt, aIdx) => (
                          <span
                            key={aIdx}
                            style={{
                              background: '#e2e8f0',
                              color: '#1e3a8a',
                              fontWeight: 700,
                              fontSize: '0.8rem',
                              padding: '0.35rem 0.75rem',
                              borderRadius: '7px',
                              letterSpacing: '0.01em',
                              boxShadow: '0 1px 2px rgba(0,0,0,0.02)'
                            }}
                          >
                            {formatAmount(amt)}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Card Footer: S.No and Action Buttons */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    borderTop: '1px solid #f1f5f9',
                    paddingTop: '1rem',
                    marginTop: 'auto'
                  }}>
                    <span style={{
                      fontSize: '0.85rem',
                      color: '#64748b',
                      fontWeight: 600
                    }}>
                      S.No {idx + 1}
                    </span>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <button
                        onClick={() => handleOpenConfigure(head)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.4rem',
                          background: '#ffffff',
                          border: '1px solid #cbd5e1',
                          borderRadius: '8px',
                          padding: '0.45rem 0.85rem',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: '#334155',
                          cursor: 'pointer',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = '#f8fafc';
                          e.currentTarget.style.borderColor = '#94a3b8';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = '#ffffff';
                          e.currentTarget.style.borderColor = '#cbd5e1';
                        }}
                      >
                        <SlidersHorizontal size={14} style={{ color: '#475569' }} />
                        <span>Configure</span>
                      </button>

                      <button
                        onClick={() => setHeadToDelete(head)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: '#ffffff',
                          border: '1px solid #fecaca',
                          borderRadius: '8px',
                          padding: '0.45rem 0.6rem',
                          color: '#ef4444',
                          cursor: 'pointer',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = '#fef2f2';
                          e.currentTarget.style.borderColor = '#f87171';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = '#ffffff';
                          e.currentTarget.style.borderColor = '#fecaca';
                        }}
                        title="Delete Fee Head"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ====== Fee Packages: total-amount dropdown options for the accountant ====== */}
        <div style={{
          background: '#ffffff',
          borderRadius: '18px',
          border: '1px solid #e2e8f0',
          padding: '1.75rem 2rem',
          boxShadow: '0 4px 18px -4px rgba(15, 23, 42, 0.05), 0 2px 6px -2px rgba(15, 23, 42, 0.03)',
          marginTop: '2rem'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
            marginBottom: '1.25rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.9rem' }}>
              <div style={{
                width: '44px',
                height: '44px',
                borderRadius: '12px',
                background: '#eff6ff',
                border: '1px solid #dbeafe',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                <Package size={22} style={{ color: '#2563eb' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>
                  Fee Packages
                </h2>
                <p style={{ margin: '0.15rem 0 0 0', fontSize: '0.8125rem', color: '#64748b' }}>
                  Pre-approved total-amount combinations. The accountant's fee desk offers only these
                  totals — selecting one fills every fee head automatically.
                </p>
              </div>
            </div>

            <button
              onClick={handleOpenPackageAdd}
              style={{
                height: '42px',
                padding: '0 1.25rem',
                borderRadius: '10px',
                background: '#2563eb',
                color: '#ffffff',
                border: 'none',
                fontWeight: 600,
                fontSize: '0.85rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                boxShadow: '0 2px 6px rgba(37, 99, 235, 0.3)',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#1d4ed8'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#2563eb'}
            >
              <Plus size={17} />
              <span>Add Package</span>
            </button>
          </div>

          {feePackages.length === 0 ? (
            <div style={{
              padding: '2.25rem 1.5rem',
              textAlign: 'center',
              color: '#64748b',
              background: '#f8fafc',
              border: '1px dashed #cbd5e1',
              borderRadius: '12px'
            }}>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#334155' }}>
                No fee packages configured yet
              </div>
              <div style={{ fontSize: '0.8125rem', marginTop: '0.35rem', lineHeight: 1.6 }}>
                Until you create packages here, the accountant's Total dropdown will be empty
                and fees cannot be set. Click <strong>'+ Add Package'</strong> to define one combination
                (each head's value must come from its allowed presets).
              </div>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: '1.25rem',
              alignItems: 'stretch'
            }}>
              {feePackages.map((pkg) => (
                <div
                  key={pkg.id}
                  style={{
                    background: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '16px',
                    padding: '1.35rem 1.5rem',
                    boxShadow: '0 4px 16px -2px rgba(15, 23, 42, 0.04)',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'box-shadow 0.2s ease, transform 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = '0 10px 24px -4px rgba(15, 23, 42, 0.08)';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = '0 4px 16px -2px rgba(15, 23, 42, 0.04)';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.6rem' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{
                        fontSize: '0.65rem', fontWeight: 800, letterSpacing: '0.06em',
                        color: '#2563eb', textTransform: 'uppercase'
                      }}>
                        {pkg.academic_year_code || ''}
                      </div>
                      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', margin: '0.15rem 0 0 0' }}>
                        {pkg.name}
                      </h3>
                    </div>
                    <span style={{
                      background: pkg.is_active ? '#ecfdf5' : '#f1f5f9',
                      color: pkg.is_active ? '#15803d' : '#64748b',
                      border: `1px solid ${pkg.is_active ? '#bbf7d0' : '#e2e8f0'}`,
                      fontSize: '0.625rem', fontWeight: 800, letterSpacing: '0.04em',
                      textTransform: 'uppercase', padding: '0.15rem 0.5rem',
                      borderRadius: '9999px', whiteSpace: 'nowrap', flexShrink: 0
                    }}>
                      {pkg.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </span>
                  </div>

                  {/* Total the accountant sees */}
                  <div style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '10px',
                    padding: '0.75rem 1rem',
                    margin: '0.9rem 0'
                  }}>
                    <div style={{
                      fontSize: '0.65rem', fontWeight: 800, letterSpacing: '0.06em',
                      color: '#64748b', textTransform: 'uppercase'
                    }}>
                      Dropdown Total
                    </div>
                    <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#1d4ed8', marginTop: '0.1rem' }}>
                      {formatAmount(pkg.total)}
                    </div>
                  </div>

                  {/* Breakdown pills */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '1rem' }}>
                    {(Array.isArray(pkg.items_resolved) ? pkg.items_resolved : []).map((it, iIdx) => (
                      <span
                        key={`${pkg.id}-${iIdx}`}
                        style={{
                          background: it.is_valid ? '#eff6ff' : '#fef2f2',
                          color: it.is_valid ? '#1e3a8a' : '#991b1b',
                          border: `1px solid ${it.is_valid ? '#bfdbfe' : '#fecaca'}`,
                          fontWeight: 600,
                          fontSize: '0.75rem',
                          padding: '0.3rem 0.6rem',
                          borderRadius: '7px'
                        }}
                      >
                        {it.head_name}: {formatAmount(it.amount)}
                      </span>
                    ))}
                  </div>

                  <div style={{
                    display: 'flex', justifyContent: 'flex-end', gap: '0.6rem',
                    borderTop: '1px solid #f1f5f9', paddingTop: '0.9rem', marginTop: 'auto'
                  }}>
                    <button
                      onClick={() => handleOpenPackageEdit(pkg)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                        background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '8px',
                        padding: '0.45rem 0.85rem', fontSize: '0.8rem', fontWeight: 600,
                        color: '#334155', cursor: 'pointer', transition: 'all 0.15s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = '#f8fafc';
                        e.currentTarget.style.borderColor = '#94a3b8';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = '#ffffff';
                        e.currentTarget.style.borderColor = '#cbd5e1';
                      }}
                    >
                      <SlidersHorizontal size={14} style={{ color: '#475569' }} />
                      <span>Edit</span>
                    </button>

                    <button
                      onClick={() => setPackageToDelete(pkg)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        background: '#ffffff', border: '1px solid #fecaca', borderRadius: '8px',
                        padding: '0.45rem 0.6rem', color: '#ef4444', cursor: 'pointer',
                        transition: 'all 0.15s ease'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = '#fef2f2';
                        e.currentTarget.style.borderColor = '#f87171';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = '#ffffff';
                        e.currentTarget.style.borderColor = '#fecaca';
                      }}
                      title="Delete Fee Package"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Add / Configure Fee Head Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={modalMode === 'add' ? 'Add Fee Head' : `Configure Fee Head: ${formData.name}`}
        maxWidth="580px"
      >
        <form onSubmit={handleSubmit} style={{ padding: '0.5rem 0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            <FormField label="Fee Head Name" required>
              <input
                type="text"
                required
                placeholder="e.g. Tuition Fee, Development Fee"
                value={formData.name}
                onChange={(e) => {
                  const val = e.target.value;
                  setFormData(prev => ({
                    ...prev,
                    name: val,
                    tag: prev.tag || val.split(' ').map(w => w[0]).join('').slice(0, 5).toUpperCase(),
                    // Keep code in sync with the name until the user edits it
                    // manually. Deriving it only once meant the very first
                    // keystroke ("O" of "Other fee...") was locked in forever,
                    // colliding with the existing "Other fee" head's code.
                    code: prev.codeTouched ? prev.code : val.replace(/\s+/g, '_').toUpperCase(),
                  }));
                }}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem' }}
              />
            </FormField>

            <FormField label="Badge Tag (e.g. TF, DF)" required>
              <input
                type="text"
                required
                placeholder="e.g. TF, DF"
                value={formData.tag}
                onChange={(e) => setFormData({ ...formData, tag: e.target.value.toUpperCase() })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontWeight: 800, textAlign: 'center', fontSize: '0.9rem' }}
              />
            </FormField>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <FormField
              label="Code (must be unique)"
              required
              hint="Auto-fills from the name. Edit it if you need something shorter (e.g. OI). Must not be used by any other fee head, in any year."
            >
              <input
                type="text"
                required
                maxLength={50}
                placeholder="e.g. TUITION_FEE, OI"
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase(), codeTouched: true })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontFamily: 'monospace', fontSize: '0.9rem' }}
              />
            </FormField>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <FormField label="Description">
              <input
                type="text"
                placeholder="e.g. Annual course instruction & faculty fee"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem' }}
              />
            </FormField>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <FormField 
              label="Allowed Dropdown Amounts (Accountant Presets)" 
              required
              hint="Enter comma-separated values in Rupees. E.g. 0, 15000, 30000, 60000"
            >
              <input
                type="text"
                required
                placeholder="0, 15000, 30000, 60000"
                value={formData.allowed_amounts_str}
                onChange={(e) => setFormData({ ...formData, allowed_amounts_str: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontFamily: 'monospace', fontWeight: 700, fontSize: '0.925rem' }}
              />
              {/* Live Preview Chips */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.65rem' }}>
                {formData.allowed_amounts_str
                  .split(',')
                  .map(s => s.trim())
                  .filter(Boolean)
                  .map((val, idx) => (
                    <span
                      key={idx}
                      style={{
                        background: '#eff6ff',
                        color: '#1d4ed8',
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        padding: '0.25rem 0.6rem',
                        borderRadius: '6px',
                        border: '1px solid #bfdbfe'
                      }}
                    >
                      {formatAmount(val)}
                    </span>
                  ))}
              </div>
            </FormField>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            <FormField label="Display Order" required>
              <input
                type="number"
                min="1"
                required
                value={formData.display_order}
                onChange={(e) => setFormData({ ...formData, display_order: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem' }}
              />
            </FormField>

            <FormField label="Academic Year" required>
              <select
                required
                value={formData.academic_year}
                onChange={(e) => setFormData({ ...formData, academic_year: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem', cursor: 'pointer' }}
              >
                {academicYears.map((ay) => (
                  <option key={ay.id} value={ay.id}>
                    {ay.code} {ay.is_current ? '(Current)' : ''}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          <div style={{ marginBottom: '1.25rem' }}>
            <FormField
              label="Fee Type"
              required
              hint="Shown on official student receipts next to this fee head."
            >
              <select
                required
                value={formData.fee_type}
                onChange={(e) => setFormData({ ...formData, fee_type: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem', cursor: 'pointer' }}
              >
                <option value="GOVERNMENT">Government Fee</option>
                <option value="INSTITUTE">Institute (Non-Government) Fee</option>
              </select>
            </FormField>
          </div>

          <div style={{ marginTop: '0.85rem', marginBottom: '1.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: 'pointer', fontSize: '0.9rem', color: '#334155' }}>
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                style={{ width: '18px', height: '18px', accentColor: '#2563eb', cursor: 'pointer' }}
              />
              <span style={{ fontWeight: 600 }}>Active (Available for accountant fee desks)</span>
            </label>
          </div>

          {modalError && (
            <div style={{
              marginBottom: '1.25rem',
              padding: '0.85rem 1.1rem',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '10px',
              color: '#991b1b',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.65rem',
            }}>
              <AlertCircle size={18} style={{ flexShrink: 0, color: '#dc2626', marginTop: '1px' }} />
              <div style={{ fontWeight: 600, lineHeight: 1.45 }}>{modalError}</div>
            </div>
          )}

          <div style={{ 
            display: 'flex', 
            justifyContent: 'flex-end', 
            gap: '0.85rem', 
            borderTop: '1px solid #f1f5f9', 
            paddingTop: '1.25rem' 
          }}>
            <button
              type="button"
              onClick={() => setShowModal(false)}
              className="edvana-btn edvana-btn-secondary"
              style={{ padding: '0.6rem 1.25rem', fontSize: '0.875rem' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="edvana-btn edvana-btn-primary"
              style={{ padding: '0.6rem 1.4rem', fontSize: '0.875rem' }}
            >
              {submitting ? 'Saving...' : modalMode === 'add' ? 'Create Fee Head' : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      {headToDelete && (
        <Modal
          isOpen={Boolean(headToDelete)}
          onClose={() => setHeadToDelete(null)}
          title="Delete Fee Head"
          maxWidth="460px"
        >
          <div style={{ padding: '0.75rem 0' }}>
            <p style={{ fontSize: '0.925rem', color: '#475569', lineHeight: 1.6, margin: '0 0 1.5rem 0' }}>
              Are you sure you want to delete <strong>"{headToDelete.name}"</strong>? This will permanently remove its selectable presets from the accountant marking desk.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem' }}>
              <button
                type="button"
                onClick={() => setHeadToDelete(null)}
                className="edvana-btn edvana-btn-secondary"
                disabled={deleting}
                style={{ padding: '0.55rem 1.15rem' }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                disabled={deleting}
                style={{
                  background: '#dc2626',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.55rem 1.25rem',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {deleting ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Add / Edit Fee Package Modal */}
      <Modal
        isOpen={showPkgModal}
        onClose={() => setShowPkgModal(false)}
        title={pkgModalMode === 'add' ? 'Add Fee Package' : `Edit Fee Package: ${pkgData.name}`}
        maxWidth="640px"
      >
        <form onSubmit={handlePackageSubmit} style={{ padding: '0.5rem 0' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
            <FormField label="Package Name" required>
              <input
                type="text"
                required
                placeholder="e.g. Full Admission Regular"
                value={pkgData.name}
                onChange={(e) => setPkgData({ ...pkgData, name: e.target.value })}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem' }}
              />
            </FormField>

            <FormField label="Academic Year" required>
              <select
                required
                value={pkgData.academic_year}
                onChange={(e) => handlePkgYearChange(e.target.value)}
                className="edvana-input"
                style={{ width: '100%', height: '42px', fontSize: '0.9rem', cursor: 'pointer' }}
              >
                {academicYears.map((ay) => (
                  <option key={ay.id} value={ay.id}>
                    {ay.code} {ay.is_current ? '(Current)' : ''}
                  </option>
                ))}
              </select>
            </FormField>
          </div>

          {/* Breakdown rows */}
          <FormField
            label="Fee Head Combination"
            required
            hint="Pick each fee head and one of its allowed preset amounts. The dropdown option shown to the accountant is the sum below."
          >
            {pkgHeadsLoading ? (
              <div style={{ padding: '1.5rem 0', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>
                Loading fee heads for {academicYears.find(y => String(y.id) === String(pkgData.academic_year))?.code || 'year'}...
              </div>
            ) : pkgHeads.length === 0 ? (
              <div style={{
                padding: '1rem 1.1rem',
                background: '#fefce8',
                border: '1px solid #fde68a',
                borderRadius: '10px',
                color: '#854d0e',
                fontSize: '0.82rem',
                lineHeight: 1.55
              }}>
                No active fee heads are configured for this academic year yet. Create the fee heads
                above first, then come back and build the package.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginTop: '0.35rem' }}>
                {(pkgData.items || []).map((item, idx) => {
                  const head = pkgHeads.find(h => String(h.id) === String(item.head));
                  const allowed = Array.isArray(head?.allowed_amounts) && head.allowed_amounts.length > 0
                    ? head.allowed_amounts
                    : null;
                  return (
                    <div key={idx} style={{ display: 'flex', gap: '0.65rem', alignItems: 'center' }}>
                      <select
                        value={item.head || ''}
                        onChange={(e) => handlePkgItemChange(idx, 'head', e.target.value)}
                        className="edvana-input"
                        style={{ flex: 2, height: '40px', fontSize: '0.85rem', cursor: 'pointer' }}
                      >
                        <option value="">— Select Fee Head —</option>
                        {pkgHeads.map((h) => (
                          <option key={h.id} value={h.id}>{h.name}</option>
                        ))}
                      </select>
                      {allowed ? (
                        <select
                          value={item.amount}
                          onChange={(e) => handlePkgItemChange(idx, 'amount', e.target.value)}
                          className="edvana-input"
                          style={{ flex: 1, height: '40px', fontSize: '0.85rem', cursor: 'pointer' }}
                        >
                          {allowed.map((amt) => (
                            <option key={amt} value={amt}>{formatAmount(amt)}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={item.amount}
                          onChange={(e) => handlePkgItemChange(idx, 'amount', e.target.value)}
                          className="edvana-input"
                          style={{ flex: 1, height: '40px', fontSize: '0.85rem' }}
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => handlePkgRemoveRow(idx)}
                        style={{
                          width: '36px', height: '40px', flexShrink: 0,
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          background: '#ffffff', border: '1px solid #fecaca',
                          borderRadius: '8px', color: '#ef4444', cursor: 'pointer',
                          transition: 'all 0.15s ease'
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = '#fef2f2'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; }}
                        title="Remove this fee head from the package"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  );
                })}

                {pkgData.items.length === 0 && (
                  <div style={{ fontSize: '0.8rem', color: '#64748b', padding: '0.35rem 0' }}>
                    No heads added yet — click “Add Fee Head Row” below.
                  </div>
                )}

                <button
                  type="button"
                  onClick={handlePkgAddRow}
                  style={{
                    alignSelf: 'flex-start',
                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                    background: '#ffffff', border: '1px dashed #94a3b8', borderRadius: '8px',
                    padding: '0.45rem 0.9rem', fontSize: '0.8rem', fontWeight: 600,
                    color: '#334155', cursor: 'pointer', transition: 'all 0.15s ease'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#f8fafc'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; }}
                >
                  <Plus size={14} /> Add Fee Head Row
                </button>

                {/* Live sum = the accountant's dropdown value */}
                <div style={{
                  marginTop: '0.35rem',
                  background: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  borderRadius: '10px',
                  padding: '0.7rem 1rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <span style={{
                    fontSize: '0.6875rem', fontWeight: 800, letterSpacing: '0.06em',
                    color: '#1d4ed8', textTransform: 'uppercase'
                  }}>
                    Total (Accountant Dropdown Option)
                  </span>
                  <span style={{ fontSize: '1.05rem', fontWeight: 800, color: '#1d4ed8' }}>
                    {formatAmount(pkgLiveTotal)}
                  </span>
                </div>
              </div>
            )}
          </FormField>

          <div style={{ marginTop: '1rem', marginBottom: '1.25rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', cursor: 'pointer', fontSize: '0.9rem', color: '#334155' }}>
              <input
                type="checkbox"
                checked={pkgData.is_active}
                onChange={(e) => setPkgData({ ...pkgData, is_active: e.target.checked })}
                style={{ width: '18px', height: '18px', accentColor: '#2563eb', cursor: 'pointer' }}
              />
              <span style={{ fontWeight: 600 }}>Active (visible at the accountant fee desk)</span>
            </label>
          </div>

          {pkgError && (
            <div style={{
              marginBottom: '1.25rem',
              padding: '0.85rem 1.1rem',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '10px',
              color: '#991b1b',
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.65rem'
            }}>
              <AlertCircle size={18} style={{ flexShrink: 0, color: '#dc2626', marginTop: '1px' }} />
              <div style={{ fontWeight: 600, lineHeight: 1.45 }}>{pkgError}</div>
            </div>
          )}

          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '0.85rem',
            borderTop: '1px solid #f1f5f9',
            paddingTop: '1.25rem'
          }}>
            <button
              type="button"
              onClick={() => setShowPkgModal(false)}
              className="edvana-btn edvana-btn-secondary"
              style={{ padding: '0.6rem 1.25rem', fontSize: '0.875rem' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pkgSubmitting}
              className="edvana-btn edvana-btn-primary"
              style={{ padding: '0.6rem 1.4rem', fontSize: '0.875rem' }}
            >
              {pkgSubmitting ? 'Saving...' : pkgModalMode === 'add' ? 'Create Package' : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Fee Package Confirmation Modal */}
      {packageToDelete && (
        <Modal
          isOpen={Boolean(packageToDelete)}
          onClose={() => setPackageToDelete(null)}
          title="Delete Fee Package"
          maxWidth="460px"
        >
          <div style={{ padding: '0.75rem 0' }}>
            <p style={{ fontSize: '0.925rem', color: '#475569', lineHeight: 1.6, margin: '0 0 1.5rem 0' }}>
              Are you sure you want to delete <strong>"{packageToDelete.name}"</strong>
              ({formatAmount(packageToDelete.total)})? The accountant will no longer be able to select
              this total at the fee desk.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.85rem' }}>
              <button
                type="button"
                onClick={() => setPackageToDelete(null)}
                className="edvana-btn edvana-btn-secondary"
                disabled={pkgDeleting}
                style={{ padding: '0.55rem 1.15rem' }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePackageDeleteConfirm}
                disabled={pkgDeleting}
                style={{
                  background: '#dc2626',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.55rem 1.25rem',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                {pkgDeleting ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
