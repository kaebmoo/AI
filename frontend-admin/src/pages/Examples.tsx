import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Switch, Tag, message, Popconfirm, Card } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, CopyOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getExamples, createExample, updateExample, deleteExample } from '../services/examples';
import type { GoldenExample } from '../services/examples';
import type { ColumnsType } from 'antd/es/table';

const { TextArea } = Input;

const Examples: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [searchText, setSearchText] = useState('');
    const [form] = Form.useForm();
    const queryClient = useQueryClient();
    const [selectedCategory] = useState<string | undefined>(undefined);

    const { data, isLoading } = useQuery({
        queryKey: ['examples', selectedCategory],
        queryFn: () => getExamples({ category: selectedCategory })
    });

    const createMutation = useMutation({
        mutationFn: createExample,
        onSuccess: () => {
            message.success('Example created successfully');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['examples'] });
            queryClient.invalidateQueries({ queryKey: ['categories'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create example: ${error.response?.data?.detail || error.message}`);
        }
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateExample(id, data),
        onSuccess: () => {
            message.success('Example updated successfully');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['examples'] });
            queryClient.invalidateQueries({ queryKey: ['categories'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update example: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: deleteExample,
        onSuccess: () => {
            message.success('Example deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['examples'] });
            queryClient.invalidateQueries({ queryKey: ['categories'] });
        }
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            difficulty: 'medium'
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: GoldenExample) => {
        setEditingId(record.id);
        form.setFieldsValue(record);
        setIsModalVisible(true);
    };

    const handleDelete = (id: number) => {
        deleteMutation.mutate(id);
    };

    const handleOk = () => {
        form.validateFields().then(values => {
            if (editingId) {
                updateMutation.mutate({ id: editingId, data: values });
            } else {
                createMutation.mutate(values);
            }
        });
    };

    const columns: ColumnsType<GoldenExample> = [
        {
            title: 'Question Pattern',
            dataIndex: 'question_pattern',
            key: 'question_pattern',
            width: 300,
            ellipsis: true,
        },
        {
            title: 'Expected SQL',
            dataIndex: 'expected_sql',
            key: 'expected_sql',
            width: 300,
            ellipsis: true,
            render: (text: string) => <code style={{ fontSize: '12px', color: '#1677ff' }}>{text}</code>
        },
        {
            title: 'Category',
            dataIndex: 'category',
            key: 'category',
            render: (text) => text ? <Tag>{text}</Tag> : '-',
            filters: data?.categories?.map(c => ({ text: c, value: c })),
            onFilter: (value, record) => record.category === value,
        },
        {
            title: 'Usage',
            dataIndex: 'usage_count',
            key: 'usage_count',
            sorter: (a, b) => a.usage_count - b.usage_count,
            width: 80,
            align: 'center',
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 80,
            render: (active: boolean) => (
                <Tag color={active ? 'success' : 'default'}>{active ? 'Active' : 'Inactive'}</Tag>
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 100,
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete Example"
                        description="Are you sure you want to delete this example?"
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
                <h2 style={{ margin: 0 }}>Golden Examples (Few-Shot)</h2>
                <Space>
                    <Input.Search
                        placeholder="Search question or SQL..."
                        allowClear
                        onSearch={value => setSearchText(value)}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 300 }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                        Add New Example
                    </Button>
                </Space>
            </div>

            <Table
                columns={columns}
                dataSource={data?.examples.filter((ex: GoldenExample) => {
                    if (!searchText) return true;
                    const lowerSearch = searchText.toLowerCase();
                    return (
                        ex.question_pattern.toLowerCase().includes(lowerSearch) ||
                        ex.expected_sql.toLowerCase().includes(lowerSearch) ||
                        (ex.category && ex.category.toLowerCase().includes(lowerSearch))
                    );
                })}
                rowKey="id"
                loading={isLoading}
                expandable={{
                    expandedRowRender: (record) => (
                        <Card size="small" style={{ margin: 0 }}>
                            <p><strong>Expected SQL:</strong></p>
                            <div style={{ position: 'relative' }}>
                                <pre style={{ background: '#f0f2f5', padding: 12, borderRadius: 4, overflowX: 'auto' }}>
                                    {record.expected_sql}
                                </pre>
                                <Button
                                    type="text"
                                    icon={<CopyOutlined />}
                                    size="small"
                                    style={{ position: 'absolute', top: 4, right: 4 }}
                                    onClick={() => {
                                        navigator.clipboard.writeText(record.expected_sql);
                                        message.success('Copied to clipboard');
                                    }}
                                />
                            </div>
                        </Card>
                    ),
                    rowExpandable: () => true,
                }}
            />

            <Modal
                title={editingId ? "Edit Example" : "Create New Example"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? "Update" : "Create"}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={800}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <Form.Item
                        name="question_pattern"
                        label="Question Pattern"
                        rules={[{ required: true, message: 'Please enter question pattern' }]}
                    >
                        <TextArea rows={2} placeholder="e.g. รายได้รวมเดือนมกราคมแบ่งตามฝ่าย" />
                    </Form.Item>

                    <Form.Item
                        name="category"
                        label="Category"
                    >
                        <Input placeholder="e.g. Revenue, Growth, Optimization" />
                    </Form.Item>

                    <Form.Item
                        name="expected_sql"
                        label="Expected SQL Query"
                        rules={[{ required: true, message: 'Please enter SQL query' }]}
                    >
                        <TextArea rows={6} style={{ fontFamily: 'monospace' }} placeholder="SELECT * FROM ..." />
                    </Form.Item>

                    <Form.Item
                        name="is_active"
                        label="Active Status"
                        valuePropName="checked"
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default Examples;
