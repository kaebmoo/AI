import React, { useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, InputNumber, Tag, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getMappings, createMapping, updateMapping, deleteMapping } from '../services/mappings';
import type { SemanticMapping } from '../services/mappings';
import type { ColumnsType } from 'antd/es/table';

const { Option } = Select;
const { TextArea } = Input;

const Mappings: React.FC = () => {
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form] = Form.useForm();
    const queryClient = useQueryClient();
    const [searchText, setSearchText] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['mappings'],
        queryFn: () => getMappings()
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
            keyword_type: 'term'
        });
        setIsModalVisible(true);
    };

    const handleEdit = (record: SemanticMapping) => {
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
            title: 'Target Column',
            dataIndex: 'target_column',
            key: 'target_column',
        },
        {
            title: 'Condition',
            dataIndex: 'target_condition',
            key: 'target_condition',
            ellipsis: true,
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
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
                <h2 style={{ margin: 0 }}>Semantic Mappings</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    Add New Mapping
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={data?.mappings}
                rowKey="id"
                loading={isLoading}
                scroll={{ x: 1000 }}
                pagination={{ pageSize: 10 }}
            />

            <Modal
                title={editingId ? "Edit Mapping" : "Create New Mapping"}
                open={isModalVisible}
                onOk={handleOk}
                onCancel={() => setIsModalVisible(false)}
                okText={editingId ? "Update" : "Create"}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
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
                        <Input />
                    </Form.Item>

                    <Form.Item
                        name="keyword_type"
                        label="Type"
                        rules={[{ required: true, message: 'Please select type' }]}
                    >
                        <Select>
                            <Option value="abbreviation">Abbreviation</Option>
                            <Option value="term">Term</Option>
                            <Option value="synonym">Synonym</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="target_column"
                        label="Target Column"
                    >
                        <Input placeholder="e.g. department_id" />
                    </Form.Item>

                    <Form.Item
                        name="target_condition"
                        label="SQL Condition"
                        tooltip="Optional condition, e.g. = 'IT'"
                    >
                        <Input placeholder="e.g. = 'IT'" />
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="Description"
                    >
                        <TextArea rows={2} />
                    </Form.Item>

                    <Form.Item
                        name="priority"
                        label="Priority"
                        initialValue={0}
                    >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
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

export default Mappings;
