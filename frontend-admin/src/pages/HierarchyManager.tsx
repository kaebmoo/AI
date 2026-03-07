import { useState, useEffect, useCallback } from 'react';
import {
    Card, Select, Table, Tag, Button, Space, Input, Modal, Form,
    Tabs, Popconfirm, message, Alert, Tooltip, Typography, Upload, Descriptions, Badge,
} from 'antd';
import {
    SyncOutlined, PlusOutlined, DeleteOutlined, EditOutlined,
    WarningOutlined, BranchesOutlined, UploadOutlined, InfoCircleOutlined,
    DiffOutlined, QuestionCircleOutlined,
} from '@ant-design/icons';
import * as hierarchyApi from '../services/hierarchy';
import type {
    HierarchyContextSummary, HierarchyLevel, HierarchyValue,
    HierarchyDiff, UnmatchedKeyword, AvailableView,
} from '../services/hierarchy';

const { Text, Paragraph } = Typography;

// --- Help texts ---
const HELP = {
    page: 'จัดการ Master Data ที่ AI ใช้ในการแปลงคำถามเป็น SQL — กำหนดลำดับชั้นข้อมูล (Hierarchy), ค่าจริงในฐานข้อมูล, และ aliases สำหรับการค้นหา',
    levels: 'กำหนดลำดับชั้นของข้อมูล เช่น กลุ่มธุรกิจ > กลุ่มบริการ > บริการ — AI ใช้ข้อมูลนี้ตัดสินว่าควร filter ที่ column ไหน และ group by อะไร',
    values: 'ค่าจริงในแต่ละระดับ พร้อม aliases ที่ผู้ใช้อาจพิมพ์ค้นหา เช่น "fixed line" → บริการโทรศัพท์ประจำที่ — AI ใช้ aliases ช่วยจับคู่คำถามกับ column/value ที่ถูกต้อง',
    unmatched: 'Keywords ที่ AI ใช้ LIKE ค้นหาแต่ไม่มี alias ตรงกัน — ยิ่งมี count สูง ยิ่งควรเพิ่มเป็น alias เพื่อให้ AI ทำงานแม่นยำขึ้น',
    extract: 'ดึงค่าจริงจากฐานข้อมูล (DISTINCT values) มาสร้าง hierarchy อัตโนมัติ — ค่าที่ admin แก้ไขเอง (manual) จะไม่ถูกทับ',
    diff: 'เปรียบเทียบ master data กับข้อมูลจริงในฐานข้อมูล — แสดงค่าที่เพิ่มใหม่ (new) และค่าที่หายไป (missing)',
    importCsv: 'นำเข้า hierarchy values จากไฟล์ CSV — ระบุว่า column ไหนในไฟล์เป็นค่า (value), ค่าแม่ (parent), และ aliases แล้วระบบจะบันทึกเป็น source=manual',
};

function HelpTip({ text }: { text: string }) {
    return <Tooltip title={text}><QuestionCircleOutlined style={{ color: '#999', marginLeft: 6 }} /></Tooltip>;
}

export default function HierarchyManager() {
    const [contexts, setContexts] = useState<HierarchyContextSummary[]>([]);
    const [selectedContext, setSelectedContext] = useState<string>('');
    const [levels, setLevels] = useState<HierarchyLevel[]>([]);
    const [values, setValues] = useState<HierarchyValue[]>([]);
    const [valuePagination, setValuePagination] = useState({ total: 0, page: 1 });
    const [unmatched, setUnmatched] = useState<UnmatchedKeyword[]>([]);
    const [diff, setDiff] = useState<HierarchyDiff | null>(null);
    const [loading, setLoading] = useState(false);
    const [searchText, setSearchText] = useState('');
    const [selectedLevel, setSelectedLevel] = useState<number | undefined>();
    const [parentFilter, setParentFilter] = useState<string | undefined>();
    const [editModal, setEditModal] = useState<{ open: boolean; value?: HierarchyValue }>({ open: false });
    const [levelModal, setLevelModal] = useState<{ open: boolean; level?: HierarchyLevel }>({ open: false });
    const [importModal, setImportModal] = useState(false);
    const [importFile, setImportFile] = useState<File | null>(null);
    const [bootstrapModal, setBootstrapModal] = useState(false);
    const [availableViews, setAvailableViews] = useState<AvailableView[]>([]);
    const [form] = Form.useForm();
    const [levelForm] = Form.useForm();
    const [importForm] = Form.useForm();
    const [bootstrapForm] = Form.useForm();

    // --- Data loading ---
    const loadContexts = useCallback(async () => {
        try {
            const res = await hierarchyApi.getContexts();
            setContexts(res.data);
            if (res.data.length > 0 && !selectedContext) {
                setSelectedContext(res.data[0].context_name);
            }
        } catch { /* ignore */ }
    }, [selectedContext]);

    const loadLevels = useCallback(async () => {
        if (!selectedContext) return;
        try {
            const res = await hierarchyApi.getLevels(selectedContext);
            setLevels(res.data);
        } catch { /* ignore */ }
    }, [selectedContext]);

    const loadValues = useCallback(async (page = 1) => {
        if (!selectedContext) return;
        setLoading(true);
        try {
            const res = await hierarchyApi.getValues(selectedContext, {
                level: selectedLevel,
                parent_value: parentFilter,
                search: searchText || undefined,
                page,
                page_size: 100,
            });
            setValues(res.data.items);
            setValuePagination({ total: res.data.total, page: res.data.page });
        } catch { /* ignore */ }
        setLoading(false);
    }, [selectedContext, selectedLevel, parentFilter, searchText]);

    const loadUnmatched = useCallback(async () => {
        try {
            const res = await hierarchyApi.getUnmatchedKeywords(selectedContext || undefined);
            setUnmatched(res.data);
        } catch { /* ignore */ }
    }, [selectedContext]);

    useEffect(() => { loadContexts(); }, [loadContexts]);
    useEffect(() => { loadLevels(); loadValues(); loadUnmatched(); }, [selectedContext, loadLevels, loadValues, loadUnmatched]);

    // --- Actions ---
    const handleExtract = async () => {
        setLoading(true);
        try {
            await hierarchyApi.extractHierarchy(selectedContext);
            message.success('Auto-extract completed');
            loadLevels(); loadValues(); loadContexts();
        } catch { message.error('Extract failed'); }
        setLoading(false);
    };

    const handleDiff = async () => {
        if (!selectedContext) return;
        setLoading(true);
        try {
            const res = await hierarchyApi.getDiff(selectedContext);
            setDiff(res.data);
        } catch { message.error('Diff failed'); }
        setLoading(false);
    };

    const handleSaveValue = async () => {
        const data = form.getFieldsValue();
        const aliases = (data.aliases_text || '').split(',').map((s: string) => s.trim()).filter(Boolean);
        try {
            if (editModal.value?.id) {
                await hierarchyApi.updateValue(editModal.value.id, {
                    value: data.value, parent_value: data.parent_value || null, aliases,
                });
            } else {
                await hierarchyApi.createValue(selectedContext, {
                    level: data.level, value: data.value,
                    parent_value: data.parent_value || null, aliases,
                });
            }
            message.success('Saved');
            setEditModal({ open: false }); loadValues();
        } catch { message.error('Save failed'); }
    };

    const handleDeleteValue = async (id: number) => {
        try {
            await hierarchyApi.deleteValue(id);
            message.success('Deleted'); loadValues();
        } catch { message.error('Delete failed'); }
    };

    const handleSaveLevel = async () => {
        const data = levelForm.getFieldsValue();
        const columns = (data.columns_text || '').split(',').map((s: string) => s.trim()).filter(Boolean);
        const keywords = (data.keywords_text || '').split(',').map((s: string) => s.trim()).filter(Boolean);
        try {
            await hierarchyApi.upsertLevel(selectedContext, {
                level: data.level, level_label_th: data.level_label_th,
                level_label_en: data.level_label_en, level_columns: columns,
                detection_keywords: keywords,
            });
            message.success('Level saved');
            setLevelModal({ open: false }); loadLevels();
        } catch { message.error('Save failed'); }
    };

    const handleImportCsv = async () => {
        if (!importFile || !selectedContext) return;
        const data = importForm.getFieldsValue();
        setLoading(true);
        try {
            const res = await hierarchyApi.importCsv(selectedContext, importFile, {
                level: data.level,
                value_column: data.value_column,
                parent_column: data.parent_column || undefined,
                alias_columns: data.alias_columns || undefined,
            });
            message.success(`Imported ${res.data.imported} values from ${res.data.filename}`);
            setImportFile(null);
            importForm.resetFields();
            setImportModal(false);
            loadValues(); loadContexts();
        } catch (e: any) {
            message.error(e.response?.data?.detail || 'Import failed');
        }
        setLoading(false);
    };

    const handleBootstrap = async () => {
        const data = bootstrapForm.getFieldsValue();
        if (!data.context_name || !data.view_name) return;
        setLoading(true);
        try {
            const res = await hierarchyApi.bootstrapHierarchy(data.context_name, data.view_name);
            const levelsCount = res.data.levels_created?.length || 0;
            message.success(`Created ${levelsCount} levels and extracted values for "${data.context_name}"`);
            setBootstrapModal(false);
            bootstrapForm.resetFields();
            loadContexts();
            setSelectedContext(data.context_name);
        } catch (e: any) {
            message.error(e.response?.data?.detail || 'Bootstrap failed');
        }
        setLoading(false);
    };

    const loadAvailableViews = async () => {
        try {
            const res = await hierarchyApi.getAvailableViews();
            setAvailableViews(res.data);
        } catch { /* ignore */ }
    };

    const handleResolveUnmatched = async (kw: UnmatchedKeyword) => {
        try {
            await hierarchyApi.resolveUnmatched(kw.keyword, kw.context_name);
            message.success('Resolved'); loadUnmatched();
        } catch { message.error('Failed'); }
    };

    // --- Column definitions ---
    const levelColumns = [
        { title: 'Level', dataIndex: 'level', width: 60 },
        { title: 'Label (TH)', dataIndex: 'level_label_th' },
        { title: 'Label (EN)', dataIndex: 'level_label_en' },
        { title: 'Columns', dataIndex: 'level_columns', render: (v: string[]) => v?.join(', ') },
        { title: 'Keywords', dataIndex: 'detection_keywords', render: (v: string[]) => v?.slice(0, 3).map(k => <Tag key={k}>{k}</Tag>) },
        { title: 'Values', dataIndex: 'value_count', width: 70 },
        { title: 'Source', dataIndex: 'source', width: 70, render: (s: string) => <Tag color={s === 'manual' ? 'blue' : 'default'}>{s}</Tag> },
        {
            title: '', width: 80, render: (_: any, record: HierarchyLevel) => (
                <Button size="small" icon={<EditOutlined />} onClick={() => {
                    setLevelModal({ open: true, level: record });
                    levelForm.setFieldsValue({
                        ...record,
                        columns_text: record.level_columns?.join(', '),
                        keywords_text: record.detection_keywords?.join(', '),
                    });
                }} />
            ),
        },
    ];

    const valueColumns = [
        { title: 'Level', dataIndex: 'level', width: 50 },
        { title: 'Value', dataIndex: 'value', ellipsis: true },
        { title: 'Parent', dataIndex: 'parent_value', ellipsis: true,
          render: (v: string) => v ? <a onClick={() => { setParentFilter(v); loadValues(); }}>{v}</a> : '-' },
        { title: 'Aliases', dataIndex: 'aliases', render: (v: string[]) => v?.slice(0, 3).map(a => <Tag key={a}>{a}</Tag>) },
        { title: 'Children', dataIndex: 'children_count', width: 70,
          render: (v: number, record: HierarchyValue) => v > 0 ?
            <a onClick={() => { setParentFilter(record.value); setSelectedLevel(record.level + 1); loadValues(); }}>{v}</a> : 0 },
        { title: 'Source', dataIndex: 'source', width: 70, render: (s: string) => <Tag color={s === 'manual' ? 'blue' : 'default'}>{s}</Tag> },
        {
            title: '', width: 100, render: (_: any, record: HierarchyValue) => (
                <Space size="small">
                    <Button size="small" icon={<EditOutlined />} onClick={() => {
                        setEditModal({ open: true, value: record });
                        form.setFieldsValue({ ...record, aliases_text: record.aliases?.join(', ') });
                    }} />
                    <Popconfirm title="Delete?" onConfirm={() => handleDeleteValue(record.id)}>
                        <Button size="small" icon={<DeleteOutlined />} danger />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    const unmatchedColumns = [
        { title: 'Keyword', dataIndex: 'keyword' },
        { title: 'Context', dataIndex: 'context_name', width: 120 },
        { title: 'Count', dataIndex: 'occurrence_count', width: 60,
          sorter: (a: UnmatchedKeyword, b: UnmatchedKeyword) => a.occurrence_count - b.occurrence_count,
          defaultSortOrder: 'descend' as const },
        { title: 'Last Question', dataIndex: 'last_question', ellipsis: true },
        {
            title: '', width: 170, render: (_: any, record: UnmatchedKeyword) => (
                <Space size="small">
                    <Button size="small" type="primary" onClick={() => {
                        setEditModal({ open: true });
                        form.setFieldsValue({ value: '', aliases_text: record.keyword, level: 0 });
                    }}>Add as Alias</Button>
                    <Popconfirm title="Mark as resolved?" onConfirm={() => handleResolveUnmatched(record)}>
                        <Button size="small">Resolve</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    // --- Context summary ---
    const currentCtx = contexts.find(c => c.context_name === selectedContext);

    return (
        <div style={{ padding: 24 }}>
            <Card
                title={<><BranchesOutlined /> Master Data & Hierarchy Management <HelpTip text={HELP.page} /></>}
                extra={
                    <Space>
                        <Select
                            value={selectedContext}
                            onChange={v => { setSelectedContext(v); setParentFilter(undefined); setSelectedLevel(undefined); setDiff(null); }}
                            style={{ width: 220 }}
                            placeholder="Select context"
                        >
                            {contexts.map(c => (
                                <Select.Option key={c.context_name} value={c.context_name}>
                                    {c.context_name} ({c.value_count})
                                </Select.Option>
                            ))}
                        </Select>
                        <Tooltip title={HELP.extract}>
                            <Button icon={<SyncOutlined />} onClick={handleExtract} loading={loading}>Extract from Data</Button>
                        </Tooltip>
                        <Tooltip title={HELP.diff}>
                            <Button icon={<DiffOutlined />} onClick={handleDiff}>Show Diff</Button>
                        </Tooltip>
                        <Tooltip title={HELP.importCsv}>
                            <Button icon={<UploadOutlined />} onClick={() => { setImportModal(true); importForm.resetFields(); setImportFile(null); }}>
                                Import CSV
                            </Button>
                        </Tooltip>
                        <Tooltip title="สร้าง hierarchy ใหม่จาก view/table — ตรวจจับ columns อัตโนมัติ">
                            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setBootstrapModal(true); bootstrapForm.resetFields(); loadAvailableViews(); }}>
                                New Context
                            </Button>
                        </Tooltip>
                    </Space>
                }
            >
                {/* Empty state — no contexts yet */}
                {contexts.length === 0 && !loading && (
                    <Alert
                        type="info" showIcon
                        message="ยังไม่มี Hierarchy Context"
                        description={
                            <div>
                                <p>กดปุ่ม <strong>New Context</strong> เพื่อสร้าง hierarchy ใหม่จาก view/table ในฐานข้อมูล</p>
                                <p>หรือ run command line: <code>python scripts/extract_hierarchy.py</code></p>
                            </div>
                        }
                        style={{ marginBottom: 16 }}
                    />
                )}

                {/* Context summary bar */}
                {currentCtx && (
                    <Descriptions size="small" column={4} style={{ marginBottom: 16 }}>
                        <Descriptions.Item label="Context">{currentCtx.context_name}</Descriptions.Item>
                        <Descriptions.Item label="Levels">{currentCtx.level_count}</Descriptions.Item>
                        <Descriptions.Item label="Values">{currentCtx.value_count}</Descriptions.Item>
                        <Descriptions.Item label="Source">
                            <Tag color="blue">{currentCtx.manual_count} manual</Tag>
                            <Tag>{currentCtx.auto_count} auto</Tag>
                        </Descriptions.Item>
                    </Descriptions>
                )}

                {/* Diff alert */}
                {diff && (
                    <Alert
                        type={diff.new_values.length > 0 ? 'warning' : 'success'}
                        message={`${diff.new_values.length} new, ${diff.missing_values.length} missing, ${diff.unchanged_count} unchanged`}
                        description={diff.new_values.length > 0 ? (
                            <div style={{ marginTop: 4 }}>
                                {diff.new_values.slice(0, 5).map(v => <Tag key={v.value} color="green">L{v.level}: {v.value}</Tag>)}
                                {diff.new_values.length > 5 && <Text type="secondary"> +{diff.new_values.length - 5} more</Text>}
                            </div>
                        ) : undefined}
                        closable onClose={() => setDiff(null)} style={{ marginBottom: 16 }}
                    />
                )}

                {/* Main tabs: Levels, Values, Unmatched */}
                <Tabs items={[
                    {
                        key: 'levels',
                        label: <>Hierarchy Levels <HelpTip text={HELP.levels} /></>,
                        children: (
                            <>
                                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                                    กำหนดลำดับชั้นข้อมูล — AI ใช้ keywords จับคู่คำถาม เช่น "กลุ่ม" จะ match กับ Level ที่มี keyword "กลุ่ม"
                                </Paragraph>
                                <Table columns={levelColumns} dataSource={levels} rowKey="level" size="small" pagination={false} />
                                <Button type="dashed" icon={<PlusOutlined />} style={{ marginTop: 8 }}
                                    onClick={() => { setLevelModal({ open: true }); levelForm.resetFields(); }}>
                                    Add Level
                                </Button>
                            </>
                        ),
                    },
                    {
                        key: 'values',
                        label: <>Values <HelpTip text={HELP.values} /></>,
                        children: (
                            <>
                                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                                    ค่าจริง + aliases — คลิก Parent เพื่อ drill-down, คลิก Children เพื่อดูรายการย่อย
                                </Paragraph>
                                <Space style={{ marginBottom: 12 }} wrap>
                                    <Input.Search placeholder="Search values/aliases" onSearch={v => setSearchText(v)}
                                        allowClear style={{ width: 250 }} />
                                    <Select value={selectedLevel} onChange={v => setSelectedLevel(v)}
                                        allowClear placeholder="All levels" style={{ width: 150 }}>
                                        {levels.map(l => <Select.Option key={l.level} value={l.level}>L{l.level}: {l.level_label_th}</Select.Option>)}
                                    </Select>
                                    {parentFilter && <Tag closable onClose={() => { setParentFilter(undefined); setSelectedLevel(undefined); }}>Parent: {parentFilter}</Tag>}
                                    <Button icon={<PlusOutlined />} onClick={() => { setEditModal({ open: true }); form.resetFields(); }}>Add Value</Button>
                                </Space>
                                <Table columns={valueColumns} dataSource={values} rowKey="id" size="small" loading={loading}
                                    pagination={{
                                        total: valuePagination.total, current: valuePagination.page,
                                        pageSize: 100, showTotal: t => `${t} values`,
                                        onChange: p => loadValues(p),
                                    }} />
                            </>
                        ),
                    },
                    {
                        key: 'unmatched',
                        label: <Badge count={unmatched.length} size="small" offset={[10, 0]}>
                            <WarningOutlined /> Unmatched <HelpTip text={HELP.unmatched} />
                        </Badge>,
                        children: (
                            <>
                                <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                                    Keywords ที่ AI ใช้ LIKE ค้นหาแต่ไม่มี alias — กด "Add as Alias" เพื่อเพิ่มเป็น alias หรือ "Resolve" เพื่อข้ามไป
                                </Paragraph>
                                <Table columns={unmatchedColumns} dataSource={unmatched} rowKey="keyword" size="small"
                                    locale={{ emptyText: 'No unmatched keywords — AI matched all keywords successfully' }} />
                            </>
                        ),
                    },
                ]} />
            </Card>

            {/* Import CSV Modal */}
            <Modal
                title={<><UploadOutlined /> Import CSV — {selectedContext}</>}
                open={importModal}
                onOk={handleImportCsv}
                onCancel={() => { setImportModal(false); setImportFile(null); importForm.resetFields(); }}
                okText="Import"
                okButtonProps={{ disabled: !importFile, loading }}
                width={560}
            >
                <Alert
                    type="info" showIcon icon={<InfoCircleOutlined />}
                    message="นำเข้า hierarchy values จากไฟล์ CSV"
                    description="ระบุว่า column ไหนในไฟล์ CSV เป็นค่าหลัก (value), ค่าแม่ (parent), และ aliases — ระบบจะบันทึกเป็น source=manual ซึ่งจะไม่ถูกทับโดย auto-extract"
                    style={{ marginBottom: 16 }}
                />
                <Form form={importForm} layout="vertical">
                    <Form.Item label="CSV File" required>
                        <Upload
                            accept=".csv"
                            maxCount={1}
                            beforeUpload={(file) => { setImportFile(file); return false; }}
                            onRemove={() => setImportFile(null)}
                            fileList={importFile ? [importFile as any] : []}
                        >
                            <Button icon={<UploadOutlined />}>Select CSV File</Button>
                        </Upload>
                    </Form.Item>
                    <Form.Item name="level" label="Target Level" rules={[{ required: true, message: 'Please select a level' }]}
                        tooltip="ระดับที่จะนำเข้าข้อมูล เช่น L0 = กลุ่มธุรกิจ, L1 = กลุ่มบริการ">
                        <Select placeholder="Select level">
                            {levels.map(l => <Select.Option key={l.level} value={l.level}>L{l.level}: {l.level_label_th}</Select.Option>)}
                        </Select>
                    </Form.Item>
                    <Form.Item name="value_column" label="Value Column" rules={[{ required: true, message: 'Required' }]}
                        tooltip="ชื่อ column ใน CSV ที่เก็บค่าหลัก เช่น PRODUCT_NAME, GL_NAME">
                        <Input placeholder="e.g. PRODUCT_NAME, GL_NAME" />
                    </Form.Item>
                    <Form.Item name="parent_column" label="Parent Column"
                        tooltip="ชื่อ column ใน CSV ที่เก็บค่าแม่ (ระดับบน) — เว้นว่างถ้าเป็น top level">
                        <Input placeholder="e.g. SERVICE_GROUP, GL_GROUP (leave empty for top level)" />
                    </Form.Item>
                    <Form.Item name="alias_columns" label="Alias Columns"
                        tooltip="ชื่อ column ที่จะใช้เป็น aliases เพิ่มเติม คั่นด้วย comma — ช่วยให้ AI ค้นหาได้หลายชื่อ">
                        <Input placeholder="e.g. PRODUCT_SHORT_NAME, PRODUCT_KEY (comma-separated)" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Edit Value Modal */}
            <Modal title={editModal.value ? 'Edit Value' : 'Add Value'} open={editModal.open}
                onOk={handleSaveValue} onCancel={() => setEditModal({ open: false })} okText="Save">
                <Form form={form} layout="vertical">
                    {!editModal.value && <Form.Item name="level" label="Level" rules={[{ required: true }]}>
                        <Select>{levels.map(l => <Select.Option key={l.level} value={l.level}>L{l.level}: {l.level_label_th}</Select.Option>)}</Select>
                    </Form.Item>}
                    <Form.Item name="value" label="Value" rules={[{ required: true }]}>
                        <Input />
                    </Form.Item>
                    <Form.Item name="parent_value" label="Parent Value"
                        tooltip="ค่าแม่ระดับบน — เว้นว่างถ้าเป็น top level">
                        <Input placeholder="Leave empty for top level" />
                    </Form.Item>
                    <Form.Item name="aliases_text" label="Aliases"
                        tooltip="คำค้นหาที่ผู้ใช้อาจพิมพ์ คั่นด้วย comma — AI ใช้ aliases นี้จับคู่คำถามกับ value">
                        <Input.TextArea rows={2} placeholder="fixed line, FL, โทรศัพท์ประจำที่" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Bootstrap New Context Modal */}
            <Modal
                title={<><PlusOutlined /> New Context — Auto-detect Hierarchy</>}
                open={bootstrapModal}
                onOk={handleBootstrap}
                onCancel={() => setBootstrapModal(false)}
                okText="Create & Extract"
                okButtonProps={{ loading }}
                width={520}
            >
                <Alert
                    type="info" showIcon icon={<InfoCircleOutlined />}
                    message="สร้าง hierarchy ใหม่อัตโนมัติ"
                    description="เลือก view/table แล้วระบบจะตรวจจับ columns ที่เป็น hierarchy อัตโนมัติ สร้าง levels และดึง values ให้ทั้งหมดในขั้นตอนเดียว — admin แก้ไข keywords/aliases ได้ภายหลัง"
                    style={{ marginBottom: 16 }}
                />
                <Form form={bootstrapForm} layout="vertical">
                    <Form.Item name="context_name" label="Context Name" rules={[{ required: true }]}
                        tooltip="ชื่อ context ใหม่ เช่น expense_detail, asset, cost_center">
                        <Input placeholder="e.g. expense_detail" />
                    </Form.Item>
                    <Form.Item name="view_name" label="Source View / Table" rules={[{ required: true }]}
                        tooltip="view หรือ table ที่จะดึง hierarchy จาก">
                        <Select placeholder="Select view" showSearch optionFilterProp="children">
                            {availableViews.map(v => (
                                <Select.Option key={v.view_name} value={v.view_name}>
                                    {v.view_name} {v.display_name !== v.view_name ? `(${v.display_name})` : ''}
                                    {v.source === 'schema_contexts' ? ' — registered' : ''}
                                </Select.Option>
                            ))}
                        </Select>
                    </Form.Item>
                </Form>
            </Modal>

            {/* Edit Level Modal */}
            <Modal title={levelModal.level ? 'Edit Level' : 'Add Level'} open={levelModal.open}
                onOk={handleSaveLevel} onCancel={() => setLevelModal({ open: false })} okText="Save">
                <Form form={levelForm} layout="vertical">
                    <Form.Item name="level" label="Level Number" rules={[{ required: true }]}
                        tooltip="0 = ระดับสูงสุด (กว้างที่สุด), ตัวเลขยิ่งมาก = ยิ่งเจาะลึก">
                        <Input type="number" disabled={!!levelModal.level} />
                    </Form.Item>
                    <Form.Item name="level_label_th" label="Label (TH)" rules={[{ required: true }]}>
                        <Input placeholder="e.g. กลุ่มธุรกิจ" />
                    </Form.Item>
                    <Form.Item name="level_label_en" label="Label (EN)" rules={[{ required: true }]}>
                        <Input placeholder="e.g. Business Group" />
                    </Form.Item>
                    <Form.Item name="columns_text" label="Columns" rules={[{ required: true }]}
                        tooltip="ชื่อ column ในฐานข้อมูลที่ตรงกับ level นี้ คั่นด้วย comma">
                        <Input placeholder="BUSINESS_GROUP, BUSINESS" />
                    </Form.Item>
                    <Form.Item name="keywords_text" label="Detection Keywords" rules={[{ required: true }]}
                        tooltip="คำที่ผู้ใช้อาจพิมพ์เพื่ออ้างถึง level นี้ — AI ใช้ longest-match เลือก level ที่ตรงที่สุด">
                        <Input.TextArea rows={2} placeholder="กลุ่มธุรกิจ, business group, ธุรกิจ" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
}
