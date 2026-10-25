import React, { useEffect, useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm, Card } from 'antd';
import { EditOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getSchemaColumns, updateSchemaColumn, createSchemaColumn, deleteSchemaColumn, draftColumns, getColumnDrafts, acceptColumnDraft, rejectColumnDraft } from '../services/schema';
import type { SchemaMetadata, ColumnDraft } from '../services/schema';
import type { AxiosError } from 'axios';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;
const sourceColors: Record<string, string> = { declared: 'blue', manual: 'green', inferred: 'orange', learned: 'purple' };
const statusColors: Record<string, string> = { proposed: 'gold', rejected: 'red' };

const Schema: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [searchText, setSearchText] = useState('');
    const [selectedTable, setSelectedTable] = useState<string>();
    const [draftEdits, setDraftEdits] = useState<Record<number, string>>({});
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['schema'],
        queryFn: () => getSchemaColumns()
    });

    const { data: drafts, error: draftsError, isFetching: draftsLoading } = useQuery<ColumnDraft[], AxiosError<{ detail?: string }>>({
        queryKey: ['columnDrafts', selectedTable],
        queryFn: () => getColumnDrafts(selectedTable!),
        enabled: !!selectedTable
    });

    useEffect(() => {
        if (draftsError) {
            message.error(`โหลดคำอธิบายฉบับร่างไม่สำเร็จ: ${draftsError.response?.data?.detail || draftsError.message}`);
        }
    }, [draftsError]);

    const draftMutation = useMutation({
        mutationFn: draftColumns,
        onSuccess: (result) => {
            message.success(`เพิ่มฉบับร่างใหม่ ${result.drafted} รายการ ข้าม ${result.skipped.length} คอลัมน์`);
            return queryClient.invalidateQueries({ queryKey: ['columnDrafts', result.table] });
        },
        onError: (error: any) => {
            message.error(`ร่างคำอธิบายไม่สำเร็จ: ${error.response?.data?.detail || error.message}`);
        }
    });

    const refreshDraftsAndSchema = () => Promise.all([
        queryClient.invalidateQueries({ queryKey: ['columnDrafts'] }),
        queryClient.invalidateQueries({ queryKey: ['schema'] })
    ]);

    const acceptDraftMutation = useMutation({
        mutationFn: ({ id, description }: { id: number; description: string }) => acceptColumnDraft(id, description),
        onSuccess: () => {
            message.success('รับคำอธิบายแล้ว');
            return refreshDraftsAndSchema();
        },
        onError: (error: any) => {
            message.error(`รับคำอธิบายไม่สำเร็จ: ${error.response?.data?.detail || error.message}`);
        }
    });

    const rejectDraftMutation = useMutation({
        mutationFn: rejectColumnDraft,
        onSuccess: () => {
            message.success('ปฏิเสธคำอธิบายแล้ว');
            return refreshDraftsAndSchema();
        },
        onError: (error: any) => {
            message.error(`ปฏิเสธคำอธิบายไม่สำเร็จ: ${error.response?.data?.detail || error.message}`);
        }
    });

    const draftActionPending = acceptDraftMutation.isPending || rejectDraftMutation.isPending;

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateSchemaColumn(id, data),
        onSuccess: () => {
            message.success('Column metadata updated successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update metadata: ${error.response?.data?.detail || error.message}`);
        }
    });

    const createMutation = useMutation({
        mutationFn: (data: any) => createSchemaColumn(data),
        onSuccess: () => {
            message.success('Column created successfully');
            closeModal();
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create column: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteSchemaColumn(id),
        onSuccess: () => {
            message.success('Column deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['schema'] });
        },
        onError: (error: any) => {
            message.error(`Failed to delete column: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handleEdit = (record: SchemaMetadata) => {
        setEditingId(record.id);
        setIsCreating(false);
        form.setFieldsValue(record);
        setIsModalVisible(true);
    };

    const handleCreate = () => {
        setEditingId(null);
        setIsCreating(true);
        form.resetFields();
        // Set defaults
        form.setFieldsValue({
            data_type: 'VARCHAR',
            is_summable: false,
            is_groupable: false
        });
        setIsModalVisible(true);
    };

    const closeModal = () => {
        setIsModalVisible(false);
        setEditingId(null);
        setIsCreating(false);
        form.resetFields();
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            if (isCreating) {
                createMutation.mutate(values);
            } else if (editingId) {
                updateMutation.mutate({ id: editingId, data: values });
            }
        });
    };

    const handleDelete = (id: number) => {
        deleteMutation.mutate(id);
    };





    const columns: ColumnsType<SchemaMetadata> = [
        {
            title: 'Table',
            dataIndex: 'table_name',
            key: 'table_name',
            // sorter: (a, b) => a.table_name.localeCompare(b.table_name),
            filters: Array.from(new Set(data?.columns.map(c => c.table_name) || [])).map(t => ({ text: t, value: t })),
            onFilter: (value, record) => record.table_name === value,
            width: 150,
        },
        {
            title: 'Column',
            dataIndex: 'column_name',
            key: 'column_name',
            width: 150,
        },
        {
            title: 'Type',
            dataIndex: 'data_type',
            key: 'data_type',
            width: 100,
            render: (text) => <Tag>{text}</Tag>
        },
        {
            title: 'Display Name (TH)',
            dataIndex: 'display_name_th',
            key: 'display_name_th',
        },
        {
            title: 'Display Name (EN)',
            dataIndex: 'display_name_en',
            key: 'display_name_en',
        },
        {
            title: 'Flags',
            key: 'flags',
            width: 150,
            render: (_, record) => (
                <Space>
                    {record.is_groupable && <Tag color="blue">GROUP</Tag>}
                    {record.is_summable && <Tag color="green">SUM</Tag>}
                </Space>
            )
        },
        {
            title: 'แหล่งที่มา',
            key: 'source',
            width: 180,
            render: (_, record) => (
                <Space wrap>
                    {record.source ? <Tag color={sourceColors[record.source]}>{record.source}</Tag> : '-'}
                    {record.status && record.status !== 'active' && <Tag color={statusColors[record.status]}>{record.status}</Tag>}
                </Space>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 80,
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete this column?"
                        description="This action cannot be undone."
                        onConfirm={() => handleDelete(record.id)}
                        okText="Delete"
                        cancelText="Cancel"
                    >
                        <Button
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                        />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ margin: 0 }}>Schema Explorer</h2>
                    <p style={{ color: '#888', margin: 0 }}>Manage database column metadata for AI context.</p>
                </div>
                <Space>
                    <Input.Search
                        placeholder="Search table, column, or name..."
                        allowClear
                        onSearch={value => setSearchText(value)}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 300 }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                        Add Column
                    </Button>
                </Space>
            </div>

            <Space wrap style={{ marginBottom: 16 }}>
                <Select
                    aria-label="เลือกตาราง"
                    placeholder="เลือกตาราง"
                    showSearch
                    allowClear
                    optionFilterProp="label"
                    value={selectedTable}
                    onChange={setSelectedTable}
                    options={Array.from(new Set(data?.columns.map(c => c.table_name) || [])).map(table => ({ label: table, value: table }))}
                    style={{ minWidth: 300 }}
                />
                <Button
                    disabled={!selectedTable || draftActionPending}
                    loading={draftMutation.isPending}
                    onClick={() => selectedTable && draftMutation.mutate(selectedTable)}
                >
                    ร่างคำอธิบาย
                </Button>
            </Space>

            {selectedTable && !!drafts?.length && (
                <Card title={`คำอธิบายฉบับร่าง — ${selectedTable}`} style={{ marginBottom: 16 }}>
                    <Table<ColumnDraft>
                        rowKey="id"
                        dataSource={drafts}
                        loading={draftsLoading}
                        pagination={false}
                        scroll={{ x: 900 }}
                        columns={[
                            { title: 'คอลัมน์', dataIndex: 'column_name', width: 180 },
                            { title: 'สถานะ', key: 'status', width: 160, render: () => <Tag color="orange">inferred · proposed</Tag> },
                            {
                                title: 'ความมั่นใจ', dataIndex: 'confidence', width: 110,
                                render: (confidence: number | null) => confidence == null ? '-' : `${Math.round(confidence * 100)}%`
                            },
                            { title: 'เหตุผล', dataIndex: 'reason', width: 220 },
                            {
                                title: 'คำอธิบาย (แก้ไขได้)', key: 'description', width: 350,
                                render: (_, draft) => (
                                    <TextArea
                                        aria-label={`คำอธิบาย ${draft.column_name}`}
                                        autoSize={{ minRows: 3, maxRows: 8 }}
                                        value={draftEdits[draft.id] ?? draft.description}
                                        disabled={draftActionPending}
                                        onChange={e => setDraftEdits(previous => ({ ...previous, [draft.id]: e.target.value }))}
                                    />
                                )
                            },
                            {
                                title: 'การดำเนินการ', key: 'actions', width: 180,
                                render: (_, draft) => (
                                    <Space>
                                        <Button
                                            type="primary"
                                            disabled={draftActionPending || !(draftEdits[draft.id] ?? draft.description).trim()}
                                            loading={acceptDraftMutation.isPending && acceptDraftMutation.variables?.id === draft.id}
                                            onClick={() => acceptDraftMutation.mutate({ id: draft.id, description: draftEdits[draft.id] ?? draft.description })}
                                        >
                                            รับ
                                        </Button>
                                        <Popconfirm
                                            title="ปฏิเสธคำอธิบายฉบับร่างนี้?"
                                            okText="ปฏิเสธ"
                                            cancelText="ยกเลิก"
                                            disabled={draftActionPending}
                                            onConfirm={() => rejectDraftMutation.mutate(draft.id)}
                                        >
                                            <Button danger disabled={draftActionPending} loading={rejectDraftMutation.isPending && rejectDraftMutation.variables === draft.id}>
                                                ปฏิเสธ
                                            </Button>
                                        </Popconfirm>
                                    </Space>
                                )
                            }
                        ]}
                    />
                </Card>
            )}

            <Table
                columns={columns}
                dataSource={data?.columns.filter((col: SchemaMetadata) => {
                    if (selectedTable && col.table_name !== selectedTable) return false;
                    if (!searchText) return true;
                    const lowerSearch = searchText.toLowerCase();
                    return (
                        col.table_name.toLowerCase().includes(lowerSearch) ||
                        col.column_name.toLowerCase().includes(lowerSearch) ||
                        (col.display_name_th && col.display_name_th.toLowerCase().includes(lowerSearch)) ||
                        (col.display_name_en && col.display_name_en.toLowerCase().includes(lowerSearch)) ||
                        (col.description && col.description.toLowerCase().includes(lowerSearch))
                    );
                })}
                rowKey="id"
                loading={isLoading}
                scroll={{ x: 1000 }}
                pagination={{ pageSize: 20 }}
            />

            <Modal
                title={isCreating ? "Add New Column" : "Edit Column Metadata"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={closeModal}
                okText={isCreating ? "Create" : "Update"}
                confirmLoading={updateMutation.isPending || createMutation.isPending}
                width={700}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <div style={{ display: 'flex', gap: 16, marginBottom: 16, background: '#f5f5f5', padding: 12, borderRadius: 8 }}>
                        {isCreating ? (
                            <>
                                <Form.Item
                                    name="table_name"
                                    label="Table Name"
                                    style={{ flex: 1, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Input placeholder="e.g. users" />
                                </Form.Item>
                                <Form.Item
                                    name="column_name"
                                    label="Column Name"
                                    style={{ flex: 1, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Input placeholder="e.g. email" />
                                </Form.Item>
                                <Form.Item
                                    name="data_type"
                                    label="Data Type"
                                    style={{ width: 120, marginBottom: 0 }}
                                    rules={[{ required: true }]}
                                >
                                    <Select>
                                        <Select.Option value="VARCHAR">VARCHAR</Select.Option>
                                        <Select.Option value="INTEGER">INTEGER</Select.Option>
                                        <Select.Option value="FLOAT">FLOAT</Select.Option>
                                        <Select.Option value="BOOLEAN">BOOLEAN</Select.Option>
                                        <Select.Option value="DATE">DATE</Select.Option>
                                        <Select.Option value="TIMESTAMP">TIMESTAMP</Select.Option>
                                        <Select.Option value="TEXT">TEXT</Select.Option>
                                    </Select>
                                </Form.Item>
                            </>
                        ) : (
                            <>
                                <div style={{ flex: 1 }}><strong>Table:</strong> {form.getFieldValue('table_name')}</div>
                                <div style={{ flex: 1 }}><strong>Column:</strong> {form.getFieldValue('column_name')}</div>
                                <div style={{ width: 100 }}><strong>Type:</strong> {form.getFieldValue('data_type')}</div>
                            </>
                        )}
                    </div>

                    <Form.Item label="Display Names" style={{ marginBottom: 0 }}>
                        <Form.Item
                            name="display_name_th"
                            style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
                            label="Thai"
                        >
                            <Input placeholder="ชื่อภาษาไทย" />
                        </Form.Item>
                        <Form.Item
                            name="display_name_en"
                            style={{ display: 'inline-block', width: 'calc(50% - 8px)', margin: '0 0 0 16px' }}
                            label="English"
                        >
                            <Input placeholder="English Name" />
                        </Form.Item>
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="Description"
                    >
                        <TextArea rows={2} placeholder="Description for AI understanding" />
                    </Form.Item>

                    <Form.Item
                        name="special_notes"
                        label="Special Notes"
                    >
                        <TextArea rows={2} placeholder="Any specific logic or caveats" />
                    </Form.Item>

                    <Space size="large">
                        <Form.Item
                            name="is_groupable"
                            label="Groupable"
                            valuePropName="checked"
                        >
                            <Switch />
                        </Form.Item>
                        <Form.Item
                            name="is_summable"
                            label="Summable (Metric)"
                            valuePropName="checked"
                        >
                            <Switch />
                        </Form.Item>
                    </Space>
                </Form>
            </Modal>
        </div>
    );
};

export default Schema;
