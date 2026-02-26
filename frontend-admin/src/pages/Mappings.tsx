import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, InputNumber, Tag, message, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, GlobalOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getMappings, createMapping, updateMapping, deleteMapping, getContexts } from '../services/mappings';
import type { SemanticMapping, SchemaContext } from '../services/mappings';
import type { ColumnsType } from 'antd/es/table';

const { Option } = Select;
const { TextArea } = Input;

// Tag colours per context name (fallback to 'magenta' for unknown)
const CONTEXT_COLORS: Record<string, string> = {
    revenue: 'cyan',
    expense: 'volcano',
    'transfer price': 'geekblue',
    pl_costtype: 'purple',
};

const Mappings: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();
    const [searchText, setSearchText] = useState('');
    const [filterContext, setFilterContext] = useState<string | undefined>(undefined);

    // ── Fetch active contexts from API (no hardcode) ──────────────────────────
    const { data: contexts = [] } = useQuery<SchemaContext[]>({
        queryKey: ['schema-contexts'],
        queryFn: getContexts,
        staleTime: 5 * 60 * 1000, // cache 5 min
    });

    // ── Mappings list ─────────────────────────────────────────────────────────
    const { data, isLoading } = useQuery({
        queryKey: ['mappings', filterContext],
        queryFn: () =>
            getMappings(
                filterContext !== undefined
                    ? { context_name: filterContext === '' ? 'global' : filterContext }
                    : undefined
            ),
    });

    const createMutation = useMutation({
        mutationFn: createMapping,
        onSuccess: () => {
            message.success('Mapping created successfully');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['mappings'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create mapping: ${error.response?.data?.detail || error.message}`);
        },
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateMapping(id, data),
        onSuccess: () => {
            message.success('Mapping updated successfully');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['mappings'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update mapping: ${error.response?.data?.detail || error.message}`);
        },
    });

    const deleteMutation = useMutation({
        mutationFn: deleteMapping,
        onSuccess: () => {
            message.success('Mapping deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['mappings'] });
        },
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({ is_active: true, priority: 0, keyword_type: 'term', context_name: null });
        setIsModalVisible(true);
    };

    const handleEdit = (record: SemanticMapping) => {
        setEditingId(record.id);
        form.setFieldsValue({ ...record, context_name: record.context_name ?? null });
        setIsModalVisible(true);
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            const payload = { ...values, context_name: values.context_name || null };
            if (editingId) {
                updateMutation.mutate({ id: editingId, data: payload });
            } else {
                createMutation.mutate(payload);
            }
        });
    };

    // ── Context tag renderer ──────────────────────────────────────────────────
    const renderContextTag = (ctx: string | null | undefined, contextList: SchemaContext[]) => {
        if (!ctx) {
            return (
                <Tooltip title="ใช้ได้กับทุก context">
                    <Tag icon={<GlobalOutlined />} color="default">Global</Tag>
                </Tooltip>
            );
        }
        const found = contextList.find(c => c.name === ctx);
        const label = found?.display_name ? `${ctx} (${found.display_name})` : ctx;
        return (
            <Tooltip title={label}>
                <Tag color={CONTEXT_COLORS[ctx] ?? 'magenta'}>{ctx}</Tag>
            </Tooltip>
        );
    };

    // ── Table columns ─────────────────────────────────────────────────────────
    const columns: ColumnsType<SemanticMapping> = [
        {
            title: 'Keyword',
            dataIndex: 'keyword',
            key: 'keyword',
            sorter: (a, b) => a.keyword.localeCompare(b.keyword),
            fixed: 'left',
            filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => (
                <div style={{ padding: 8 }}>
                    <Input
                        placeholder="Search keyword"
                        value={selectedKeys[0]}
                        onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                        onPressEnter={() => confirm()}
                        style={{ marginBottom: 8, display: 'block' }}
                    />
                    <Space>
                        <Button type="primary" onClick={() => confirm()} icon={<SearchOutlined />} size="small" style={{ width: 90 }}>
                            Search
                        </Button>
                        <Button onClick={() => clearFilters && clearFilters()} size="small" style={{ width: 90 }}>
                            Reset
                        </Button>
                    </Space>
                </div>
            ),
            onFilter: (value, record) =>
                record.keyword.toLowerCase().includes((value as string).toLowerCase()),
        },
        {
            title: 'Type',
            dataIndex: 'keyword_type',
            key: 'keyword_type',
            width: 120,
            filters: [
                { text: 'Abbreviation', value: 'abbreviation' },
                { text: 'Term', value: 'term' },
                { text: 'Synonym', value: 'synonym' },
            ],
            onFilter: (value, record) => record.keyword_type === value,
            render: (type: string | undefined) => {
                if (!type) return '-';
                const color = type === 'abbreviation' ? 'blue' : type === 'synonym' ? 'green' : 'orange';
                return <Tag color={color}>{type.toUpperCase()}</Tag>;
            },
        },
        {
            title: 'Context',
            dataIndex: 'context_name',
            key: 'context_name',
            width: 140,
            render: (ctx: string | null | undefined) => renderContextTag(ctx, contexts),
        },
        {
            title: 'Target Column',
            dataIndex: 'target_column',
            key: 'target_column',
        },
        {
            title: 'Condition',
            dataIndex: 'target_condition',
            key: 'target_condition',
            ellipsis: true,
            render: (text: string, record: SemanticMapping) =>
                record.full_condition ? <Tag color="purple">Complex</Tag> : text,
        },
        {
            title: 'Full Condition',
            dataIndex: 'full_condition',
            key: 'full_condition',
            ellipsis: true,
            width: 200,
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 80,
            render: (active: boolean) => (
                <Tag color={active ? 'success' : 'error'}>{active ? 'Active' : 'Inactive'}</Tag>
            ),
        },
        {
            title: 'Actions',
            key: 'actions',
            fixed: 'right',
            width: 120,
            render: (_, record) => (
                <Space>
                    <Button type="text" icon={<EditOutlined style={{ color: '#1890ff' }} />} onClick={() => handleEdit(record)} />
                    <Popconfirm
                        title="Delete Mapping"
                        description="Are you sure you want to delete this mapping?"
                        onConfirm={() => deleteMutation.mutate(record.id)}
                        okText="Yes"
                        cancelText="No"
                    >
                        <Button type="text" icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            {/* ── Toolbar ── */}
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <h2 style={{ margin: 0 }}>Semantic Mappings</h2>

                    <Input.Search
                        placeholder="Search by keyword, target, or condition..."
                        allowClear
                        onSearch={value => setSearchText(value)}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 350 }}
                    />

                    {/* Context filter — built from API data */}
                    <Select
                        placeholder="Filter by context"
                        allowClear
                        style={{ width: 200 }}
                        onChange={(val: string) => setFilterContext(val)}
                        onClear={() => setFilterContext(undefined)}
                    >
                        {/* Global-only option */}
                        <Option value="">
                            <GlobalOutlined /> Global only (ไม่ระบุ context)
                        </Option>
                        {/* Active contexts from DB */}
                        {contexts.map(ctx => (
                            <Option key={ctx.name} value={ctx.name}>
                                <Tag color={CONTEXT_COLORS[ctx.name] ?? 'magenta'} style={{ marginRight: 4 }}>
                                    {ctx.name}
                                </Tag>
                                {ctx.display_name}
                            </Option>
                        ))}
                    </Select>
                </div>

                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    Add New Mapping
                </Button>
            </div>

            {/* ── Table ── */}
            <Table
                columns={columns}
                dataSource={data?.mappings.filter((mapping: SemanticMapping) => {
                    if (!searchText) return true;
                    const lower = searchText.toLowerCase();
                    return (
                        mapping.keyword.toLowerCase().includes(lower) ||
                        (mapping.target_column && mapping.target_column.toLowerCase().includes(lower)) ||
                        (mapping.target_condition && mapping.target_condition.toLowerCase().includes(lower)) ||
                        (mapping.description && mapping.description.toLowerCase().includes(lower)) ||
                        (mapping.context_name && mapping.context_name.toLowerCase().includes(lower))
                    );
                })}
                rowKey="id"
                loading={isLoading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10 }}
            />

            {/* ── Create / Edit Modal ── */}
            <Modal
                title={editingId ? 'Edit Mapping' : 'Create New Mapping'}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? 'Update' : 'Create'}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={600}
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="keyword"
                        label="Keyword"
                        rules={[{ required: true, message: 'Please enter keyword' }]}
                    >
                        <Input placeholder="เช่น ฝ่ายบริหารงานกลาง, นป., อสังหาริมทรัพย์" />
                    </Form.Item>

                    <Form.Item
                        name="keyword_type"
                        label="Type"
                        rules={[{ required: true, message: 'Please select type' }]}
                    >
                        <Select>
                            <Option value="abbreviation">Abbreviation — ตัวย่อ เช่น นป., กน.1</Option>
                            <Option value="term">Term — คำศัพท์/ชื่อเฉพาะ เช่น ฝ่าย, DIVISION</Option>
                            <Option value="synonym">Synonym — OR หลาย column เช่น ฝ่ายเจ้าของ+ผู้ใช้</Option>
                        </Select>
                    </Form.Item>

                    {/* ── Context dropdown — ดึงจาก API เสมอ ── */}
                    <Form.Item
                        name="context_name"
                        label="Context (ขอบเขต)"
                        tooltip="ไม่เลือก = Global ใช้ได้กับทุก context | เลือก = ใช้เฉพาะ context นั้น"
                    >
                        <Select
                            allowClear
                            placeholder="— Global (ใช้ได้ทุก context) —"
                        >
                            {contexts.map(ctx => (
                                <Option key={ctx.name} value={ctx.name}>
                                    <Tag color={CONTEXT_COLORS[ctx.name] ?? 'magenta'} style={{ marginRight: 4 }}>
                                        {ctx.name}
                                    </Tag>
                                    {ctx.display_name ?? ctx.name}
                                </Option>
                            ))}
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="target_column"
                        label="Target Column"
                        rules={[{ required: true, message: 'Please enter target column' }]}
                        tooltip="ชื่อ column ใน SQL เช่น DIVISION, owner_department, user_department"
                    >
                        <Input placeholder="เช่น DIVISION, DEPARTMENT, owner_department" />
                    </Form.Item>

                    <Form.Item
                        name="target_condition"
                        label="SQL Condition"
                        rules={[{ required: true, message: 'Please enter SQL condition' }]}
                        tooltip="ส่วน condition เช่น = 'IT' หรือ LIKE '%value%'"
                    >
                        <Input placeholder="เช่น = 'สายงานขาย'  หรือ  LIKE 'ฝ่าย%'" />
                    </Form.Item>

                    <Form.Item
                        name="full_condition"
                        label="Full SQL Condition (Advanced)"
                        tooltip="Override target column+condition ด้วย SQL expression เต็ม ใช้เมื่อต้องการ OR หลาย column"
                    >
                        <TextArea
                            rows={2}
                            placeholder="เช่น (owner_department = 'ฝ่ายบริหารงานกลาง' OR user_department = 'ฝ่ายบริหารงานกลาง')"
                        />
                    </Form.Item>

                    <Form.Item name="description" label="Description" tooltip="อธิบายความหมายของ mapping นี้">
                        <TextArea rows={2} placeholder="เช่น ฝ่ายบริหารงานกลาง — ใช้ใน Transfer Price context" />
                    </Form.Item>

                    <Form.Item
                        name="priority"
                        label="Priority (ลำดับความสำคัญ)"
                        initialValue={0}
                        tooltip="ค่าสูงกว่า = ถูกใช้ก่อน (0–100)"
                    >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                    </Form.Item>

                    <Form.Item name="is_active" label="Active Status" valuePropName="checked">
                        <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Mappings;
