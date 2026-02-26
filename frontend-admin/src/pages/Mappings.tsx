import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, InputNumber, Tag, message, Popconfirm, Tooltip } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, GlobalOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getMappings, createMapping, updateMapping, deleteMapping } from '../services/mappings';
import type { SemanticMapping } from '../services/mappings';
import type { ColumnsType } from 'antd/es/table';

const { Option } = Select;
const { TextArea } = Input;

// Known context names — admin can also type a custom one
const KNOWN_CONTEXTS = [
    { value: '', label: 'Global (all contexts)' },
    { value: 'revenue', label: 'revenue' },
    { value: 'expense', label: 'expense' },
    { value: 'transfer price', label: 'transfer price' },
    { value: 'pl_costtype', label: 'pl_costtype' },
];

const Mappings: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();
    const [searchText, setSearchText] = useState('');
    const [filterContext, setFilterContext] = useState<string | undefined>(undefined);

    const { data, isLoading } = useQuery({
        queryKey: ['mappings', filterContext],
        queryFn: () => getMappings(filterContext !== undefined ? { context_name: filterContext || 'global' } : undefined)
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
        }
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
        }
    });

    const deleteMutation = useMutation({
        mutationFn: deleteMapping,
        onSuccess: () => {
            message.success('Mapping deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['mappings'] });
        }
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            priority: 0,
            keyword_type: 'term',
            context_name: null,  // default: global
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: SemanticMapping) => {
        setEditingId(record.id);
        form.setFieldsValue({
            ...record,
            context_name: record.context_name ?? null,
        });
        setIsModalVisible(true);
    };

    const handleDelete = (id: number) => {
        deleteMutation.mutate(id);
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            // Convert empty string back to null for context_name
            const payload = {
                ...values,
                context_name: values.context_name || null,
            };
            if (editingId) {
                updateMutation.mutate({ id: editingId, data: payload });
            } else {
                createMutation.mutate(payload);
            }
        });
    };

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
                        <Button
                            type="primary"
                            onClick={() => confirm()}
                            icon={<SearchOutlined />}
                            size="small"
                            style={{ width: 90 }}
                        >
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
            }
        },
        {
            title: 'Context',
            dataIndex: 'context_name',
            key: 'context_name',
            width: 130,
            render: (ctx: string | null | undefined) => {
                if (!ctx) {
                    return (
                        <Tooltip title="ใช้ได้กับทุก context">
                            <Tag icon={<GlobalOutlined />} color="default">Global</Tag>
                        </Tooltip>
                    );
                }
                const colorMap: Record<string, string> = {
                    'revenue': 'cyan',
                    'expense': 'volcano',
                    'transfer price': 'geekblue',
                    'pl_costtype': 'purple',
                };
                return <Tag color={colorMap[ctx] ?? 'magenta'}>{ctx}</Tag>;
            }
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
            render: (text: string, record: SemanticMapping) => (
                record.full_condition ? <Tag color="purple">Complex</Tag> : text
            )
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
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            fixed: 'right',
            width: 120,
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete Mapping"
                        description="Are you sure you want to delete this mapping?"
                        onConfirm={() => handleDelete(record.id)}
                        okText="Yes"
                        cancelText="No"
                    >
                        <Button
                            type="text"
                            icon={<DeleteOutlined style={{ color: '#ff4d4f' }} />}
                        />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
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
                    <Select
                        placeholder="Filter by context"
                        allowClear
                        style={{ width: 180 }}
                        onChange={(val) => setFilterContext(val)}
                        onClear={() => setFilterContext(undefined)}
                    >
                        <Option value="">Global only</Option>
                        <Option value="revenue">revenue</Option>
                        <Option value="expense">expense</Option>
                        <Option value="transfer price">transfer price</Option>
                        <Option value="pl_costtype">pl_costtype</Option>
                    </Select>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    Add New Mapping
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={data?.mappings.filter((mapping: SemanticMapping) => {
                    if (!searchText) return true;
                    const lowerSearch = searchText.toLowerCase();
                    return (
                        mapping.keyword.toLowerCase().includes(lowerSearch) ||
                        (mapping.target_column && mapping.target_column.toLowerCase().includes(lowerSearch)) ||
                        (mapping.target_condition && mapping.target_condition.toLowerCase().includes(lowerSearch)) ||
                        (mapping.description && mapping.description.toLowerCase().includes(lowerSearch)) ||
                        (mapping.context_name && mapping.context_name.toLowerCase().includes(lowerSearch))
                    );
                })}
                rowKey="id"
                loading={isLoading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10 }}
            />

            <Modal
                title={editingId ? "Edit Mapping" : "Create New Mapping"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? "Update" : "Create"}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={600}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <Form.Item
                        name="keyword"
                        label="Keyword"
                        rules={[{ required: true, message: 'Please enter keyword' }]}
                    >
                        <Input placeholder="e.g. ฝ่ายบริหารงานกลาง, นป., อสังหาริมทรัพย์" />
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

                    <Form.Item
                        name="context_name"
                        label="Context (ขอบเขต)"
                        tooltip="ว่าง = Global ใช้ได้กับทุก context | ระบุชื่อ = ใช้เฉพาะ context นั้น เช่น 'transfer price'"
                    >
                        <Select
                            allowClear
                            placeholder="Global (ว่าง = ใช้ได้ทุก context)"
                            showSearch
                            optionFilterProp="children"
                        >
                            {KNOWN_CONTEXTS.filter(c => c.value !== '').map(ctx => (
                                <Option key={ctx.value} value={ctx.value}>{ctx.label}</Option>
                            ))}
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="target_column"
                        label="Target Column"
                        rules={[{ required: true, message: 'Please enter target column' }]}
                        tooltip="ชื่อ column ใน SQL เช่น DIVISION, owner_department, user_department"
                    >
                        <Input placeholder="e.g. DIVISION, DEPARTMENT, owner_department" />
                    </Form.Item>

                    <Form.Item
                        name="target_condition"
                        label="SQL Condition"
                        rules={[{ required: true, message: 'Please enter SQL condition' }]}
                        tooltip="ส่วน condition เช่น = 'IT' หรือ LIKE '%value%'"
                    >
                        <Input placeholder="e.g. = 'สายงานขาย'  หรือ  LIKE 'ฝ่าย%'" />
                    </Form.Item>

                    <Form.Item
                        name="full_condition"
                        label="Full SQL Condition (Advanced)"
                        tooltip="Override target column+condition ด้วย SQL expression เต็มรูปแบบ ใช้เมื่อต้องการ OR หลาย column"
                    >
                        <TextArea rows={2} placeholder="e.g. (owner_department = 'ฝ่ายบริหารงานกลาง' OR user_department = 'ฝ่ายบริหารงานกลาง')" />
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="Description"
                        tooltip="อธิบายความหมายของ mapping นี้"
                    >
                        <TextArea rows={2} placeholder="e.g. ฝ่ายบริหารงานกลาง — ใช้ใน Transfer Price context" />
                    </Form.Item>

                    <Form.Item
                        name="priority"
                        label="Priority (ลำดับความสำคัญ)"
                        initialValue={0}
                        tooltip="ค่าสูงกว่า = ถูกใช้ก่อน (0-100)"
                    >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                    </Form.Item>

                    <Form.Item
                        name="is_active"
                        label="Active Status"
                        valuePropName="checked"
                    >
                        <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Mappings;
