import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, Tag, message, Popconfirm, Card, Typography } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getRules, createRule, updateRule, deleteRule, toggleRule } from '../services/rules';
import type { BusinessRule } from '../services/rules';
import type { ColumnsType } from 'antd/es/table';

const { Option } = Select;
const { TextArea } = Input;
const { Title, Text } = Typography;

const Rules: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['rules'],
        queryFn: () => getRules()
    });

    const createMutation = useMutation({
        mutationFn: createRule,
        onSuccess: () => {
            message.success('Rule created successfully');
            setIsModalVisible(false);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        },
        onError: (error: any) => {
            message.error(`Failed to create rule: ${error.response?.data?.detail || error.message}`);
        }
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => updateRule(id, data),
        onSuccess: () => {
            message.success('Rule updated successfully');
            setIsModalVisible(false);
            setEditingId(null);
            form.resetFields();
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        },
        onError: (error: any) => {
            message.error(`Failed to update rule: ${error.response?.data?.detail || error.message}`);
        }
    });

    const deleteMutation = useMutation({
        mutationFn: deleteRule,
        onSuccess: () => {
            message.success('Rule deleted successfully');
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        }
    });

    const toggleMutation = useMutation({
        mutationFn: toggleRule,
        onSuccess: () => {
            message.success('Rule status toggled');
            queryClient.invalidateQueries({ queryKey: ['rules'] });
        }
    });

    const handleAdd = () => {
        setEditingId(null);
        form.resetFields();
        form.setFieldsValue({
            is_active: true,
            severity: 'warning'
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: BusinessRule) => {
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

    const columns: ColumnsType<BusinessRule> = [
        {
            title: 'Code',
            dataIndex: 'rule_code',
            key: 'rule_code',
            render: (text: string) => <Text code>{text}</Text>,
        },
        {
            title: 'Name',
            dataIndex: 'rule_name',
            key: 'rule_name',
        },
        {
            title: 'Severity',
            dataIndex: 'severity',
            key: 'severity',
            render: (severity: string | undefined) => {
                if (!severity) return '-';
                const colors = { error: 'red', warning: 'orange', info: 'blue' };
                return <Tag color={colors[severity as keyof typeof colors] || 'default'}>{severity.toUpperCase()}</Tag>;
            }
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
            render: (active: boolean, record) => (
                <Switch
                    checked={active}
                    onChange={() => toggleMutation.mutate(record.id)}
                    loading={toggleMutation.isPending}
                />
            )
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_, record) => (
                <Space>
                    <Button
                        type="text"
                        icon={<EditOutlined style={{ color: '#1890ff' }} />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="Delete Rule"
                        description="Are you sure you want to delete this rule?"
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
                <h2 style={{ margin: 0 }}>Business Rules</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    Add New Rule
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={data?.rules}
                rowKey="id"
                loading={isLoading}
                expandable={{
                    expandedRowRender: (record) => (
                        <Card size="small" title="Rule Details" style={{ margin: 0 }}>
                            <p><strong>Description:</strong> {record.rule_description || '-'}</p>
                            <div style={{ display: 'flex', gap: 16 }}>
                                <div style={{ flex: 1 }}>
                                    <Tag icon={<CheckCircleOutlined />} color="success">Correct SQL Example</Tag>
                                    <pre style={{ marginTop: 8, background: '#f6ffed', border: '1px solid #b7eb8f', padding: 8, borderRadius: 4 }}>
                                        {record.example_correct || 'None'}
                                    </pre>
                                </div>
                                <div style={{ flex: 1 }}>
                                    <Tag icon={<CloseCircleOutlined />} color="error">Wrong SQL Example</Tag>
                                    <pre style={{ marginTop: 8, background: '#fff1f0', border: '1px solid #ffa39e', padding: 8, borderRadius: 4 }}>
                                        {record.example_wrong || 'None'}
                                    </pre>
                                </div>
                            </div>
                        </Card>
                    ),
                    rowExpandable: () => true,
                }}
            />

            <Modal
                title={editingId ? "Edit Rule" : "Create New Rule"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? "Update" : "Create"}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
                width={700}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <Form.Item
                        name="rule_code"
                        label="Rule Code (Unique)"
                        rules={[{ required: true, message: 'Please enter rule code' }]}
                    >
                        <Input placeholder="e.g. EXCLUDE_OTHER_REVENUE" />
                    </Form.Item>

                    <Form.Item
                        name="rule_name"
                        label="Rule Name"
                        rules={[{ required: true, message: 'Please enter rule name' }]}
                    >
                        <Input placeholder="e.g. ไม่นับรายได้อื่นในการคำนวณ" />
                    </Form.Item>

                    <Form.Item
                        name="severity"
                        label="Severity"
                        rules={[{ required: true, message: 'Please select severity' }]}
                    >
                        <Select>
                            <Option value="error">Error (Must fix)</Option>
                            <Option value="warning">Warning (Should fix)</Option>
                            <Option value="info">Info (Suggestion)</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="rule_description"
                        label="Description"
                    >
                        <TextArea rows={3} />
                    </Form.Item>

                    <Form.Item
                        name="example_correct"
                        label="Correct SQL Example"
                    >
                        <TextArea rows={3} style={{ fontFamily: 'monospace' }} placeholder="SELECT ... FROM ... WHERE valid_condition" />
                    </Form.Item>

                    <Form.Item
                        name="example_wrong"
                        label="Wrong SQL Example"
                    >
                        <TextArea rows={3} style={{ fontFamily: 'monospace' }} placeholder="SELECT ... FROM ... WHERE invalid_condition" />
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

export default Rules;
