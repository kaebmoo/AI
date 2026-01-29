import React, { useState } from 'react'
import { Table, Button, Modal, Form, Input, Select, Switch, message, Tag, Space } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userService } from '../services/users'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'

const Users: React.FC = () => {
    const [isModalOpen, setIsModalOpen] = useState(false)
    const [editingUser, setEditingUser] = useState<any>(null)
    const [form] = Form.useForm()
    const queryClient = useQueryClient()

    // Fetch users
    const { data, isLoading } = useQuery({
        queryKey: ['users'],
        queryFn: userService.list
    })

    // Create mutation
    const createMutation = useMutation({
        mutationFn: userService.create,
        onSuccess: () => {
            message.success('User created successfully')
            setIsModalOpen(false)
            form.resetFields()
            queryClient.invalidateQueries({ queryKey: ['users'] })
        }
    })

    // Update mutation
    const updateMutation = useMutation({
        mutationFn: userService.update,
        onSuccess: () => {
            message.success('User updated successfully')
            setIsModalOpen(false)
            setEditingUser(null)
            form.resetFields()
            queryClient.invalidateQueries({ queryKey: ['users'] })
        }
    })

    // Delete mutation
    const deleteMutation = useMutation({
        mutationFn: userService.delete,
        onSuccess: () => {
            message.success('User deleted successfully')
            queryClient.invalidateQueries({ queryKey: ['users'] })
        }
    })

    const handleAdd = () => {
        setEditingUser(null)
        form.resetFields()
        setIsModalOpen(true)
    }

    const handleEdit = (record: any) => {
        setEditingUser(record)
        form.setFieldsValue({
            email: record.email,
            display_name: record.display_name,
            role: record.role,
            department: record.department,
            is_active: record.is_active
        })
        setIsModalOpen(true)
    }

    const handleDelete = (id: number) => {
        Modal.confirm({
            title: 'Are you sure delete this user?',
            content: 'This action cannot be undone.',
            okText: 'Yes',
            okType: 'danger',
            cancelText: 'No',
            onOk() {
                deleteMutation.mutate(id)
            }
        })
    }

    const handleOk = () => {
        form.validateFields().then(values => {
            if (editingUser) {
                updateMutation.mutate({ ...values, id: editingUser.id })
            } else {
                createMutation.mutate(values)
            }
        })
    }

    const columns = [
        {
            title: 'Display Name',
            dataIndex: 'display_name',
            key: 'display_name',
        },
        {
            title: 'Email',
            dataIndex: 'email',
            key: 'email',
        },
        {
            title: 'Role',
            dataIndex: 'role',
            key: 'role',
            render: (role: string) => (
                <Tag color={role === 'admin' ? 'red' : role === 'viewer' ? 'blue' : 'green'}>
                    {role.toUpperCase()}
                </Tag>
            )
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            key: 'is_active',
            render: (is_active: boolean) => (
                <Tag color={is_active ? 'success' : 'error'}>
                    {is_active ? 'ACTIVE' : 'INACTIVE'}
                </Tag>
            )
        },
        {
            title: 'Action',
            key: 'action',
            render: (_: any, record: any) => (
                <Space size="middle">
                    <Button icon={<EditOutlined />} onClick={() => handleEdit(record)} />
                    <Button
                        icon={<DeleteOutlined />}
                        danger
                        onClick={() => handleDelete(record.id)}
                        disabled={record.email === 'admin@ntplc.co.th'} // Prevent delete default admin
                    />
                </Space>
            ),
        },
    ]

    return (
        <div>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2>User Management</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                    Add User
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={data?.users}
                rowKey="id"
                loading={isLoading}
            />

            <Modal
                title={editingUser ? "Edit User" : "Create User"}
                open={isModalOpen}
                onOk={handleOk}
                onCancel={() => setIsModalOpen(false)}
                confirmLoading={createMutation.isPending || updateMutation.isPending}
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="email"
                        label="Email"
                        rules={[{ required: true, message: 'Please input email!' }]}
                    >
                        <Input disabled={!!editingUser} />
                    </Form.Item>

                    <Form.Item
                        name="display_name"
                        label="Display Name"
                        rules={[{ required: true, message: 'Please input display name!' }]}
                    >
                        <Input />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        label={editingUser ? "New Password (Leave blank to keep)" : "Password"}
                        rules={[{ required: !editingUser, message: 'Please input password!' }]}
                    >
                        <Input.Password />
                    </Form.Item>

                    <Form.Item
                        name="role"
                        label="Role"
                        rules={[{ required: true, message: 'Please select role!' }]}
                    >
                        <Select>
                            <Select.Option value="admin">Admin</Select.Option>
                            <Select.Option value="user">User</Select.Option>
                            <Select.Option value="viewer">Viewer</Select.Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="is_active"
                        label="Active Status"
                        valuePropName="checked"
                        initialValue={true}
                    >
                        <Switch />
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    )
}

export default Users
