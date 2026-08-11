import {
  Button,
  Checkbox,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
  Input,
  OverlayDrawer,
  Select,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowUpload24Regular,
  Delete24Regular,
  Dismiss24Regular,
  Save24Regular,
} from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import { memberApi } from "../api/memberApi";
import type {
  CompanyMember,
  IdentityContactField,
  IdentityContactKind,
  ManagedCard,
  ManagedCardInput,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { resolveApiResourceUrl } from "../lib/resourceUrl";
import { FormFeedback } from "./FormFeedback";
import { IdentityTitlesEditor } from "./IdentityTitlesEditor";

const MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024;
const CARD_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function emptyCard(cardKind: ManagedCard["cardKind"]): ManagedCardInput {
  return {
    cardKind,
    ownerUserId: "",
    displayName: "",
    title: "",
    avatarUrl: "",
    assistantName: "",
    welcomeMessage: "",
    suggestedQuestions: [],
    identityTitles: [],
    contactFields: [],
    policyVersions: {
      privacy: "",
      chatNotice: "",
      leadConsent: "",
    },
    employeeContactVisibility: [],
    templateSourceCardId: "",
    composerMode: "default",
  };
}

function cardInput(item?: ManagedCard): ManagedCardInput {
  if (!item) return emptyCard("employee");
  return {
    cardKind: item.cardKind,
    ownerUserId: item.ownerUserId,
    displayName: item.displayName,
    title: item.title,
    avatarUrl: item.avatarUrl,
    assistantName: item.assistantName,
    welcomeMessage: item.welcomeMessage,
    suggestedQuestions: item.suggestedQuestions,
    identityTitles: item.identityTitles ?? [],
    contactFields: item.contactFields ?? [],
    policyVersions: item.policyVersions,
    employeeContactVisibility: item.employeeContactVisibility ?? [],
    templateSourceCardId: "",
    composerMode: "default",
  };
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存名片时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

type CardEditorProps = {
  open: boolean;
  item?: ManagedCard;
  createKind?: ManagedCard["cardKind"];
  onClose: () => void;
  onSaved: (created?: ManagedCard) => void;
  onCustomize: (draft: CardCreationDraft) => void;
};

export type CardCreationDraft = {
  input: ManagedCardInput;
  imageFile?: File;
  avatarChanged: boolean;
  employeeMembershipId?: string;
  employeeUserId?: string;
  canonicalAvatarUrl: string;
  identityPreview: {
    displayName: string;
    title: string;
    avatarUrl?: string;
    identityTitles: string[];
    contactFields: IdentityContactField[];
  };
};

const contactKindLabels: Record<IdentityContactKind, string> = {
  phone: "电话",
  wechat: "微信 / 企业微信",
  email: "邮箱",
  location: "地址",
  website: "官网",
  other: "其他",
};

function nextContactField(kind: IdentityContactKind = "phone"): IdentityContactField {
  const suffix = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return {
    id: `contact-${suffix}`,
    kind,
    label: contactKindLabels[kind],
    value: "",
    href: "",
  };
}

export function CardEditor({
  open,
  item,
  createKind = "employee",
  onClose,
  onSaved,
  onCustomize,
}: CardEditorProps) {
  const auth = useAuth();
  const [form, setForm] = useState<ManagedCardInput>(() => emptyCard(createKind));
  const [questionsText, setQuestionsText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [imageFile, setImageFile] = useState<File>();
  const [imagePreview, setImagePreview] = useState("");
  const [avatarChanged, setAvatarChanged] = useState(false);
  const [templateSources, setTemplateSources] = useState<ManagedCard[]>([]);
  const [employees, setEmployees] = useState<CompanyMember[]>([]);
  const imageInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const input = item ? cardInput(item) : emptyCard(createKind);
    setForm(input);
    setQuestionsText(input.suggestedQuestions.join("\n"));
    setImageFile(undefined);
    setAvatarChanged(false);
    setAttempted(false);
    setError(undefined);
  }, [createKind, item, open]);

  useEffect(() => {
    if (!open || (item?.cardKind ?? createKind) !== "employee") return;
    let active = true;
    setEmployees([]);
    void memberApi.listMembers(100).then(({ items }) => {
      if (active) setEmployees(items);
    }).catch(() => {
      if (active && auth.user) {
        setEmployees([{
          membershipId: auth.user.membershipId,
          userId: auth.user.id,
          account: "当前登录员工",
          displayName: auth.user.displayName,
          role: "card_owner",
          permissions: [],
          status: "active",
          credentialEnabled: true,
          createdAt: "",
          updatedAt: "",
        }]);
      }
    });
    return () => { active = false; };
  }, [auth.user, createKind, item?.cardKind, open]);

  useEffect(() => {
    if (!open || item) return;
    let active = true;
    setTemplateSources([]);
    void adminApi.listManagedCards().then((cards) => {
      if (active) setTemplateSources(cards.filter((card) => card.cardKind === createKind));
    }).catch(() => {
      if (active) setTemplateSources([]);
    });
    return () => { active = false; };
  }, [createKind, item, open]);

  useEffect(() => {
    if (!imageFile) {
      setImagePreview("");
      return;
    }

    let active = true;
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (active && typeof reader.result === "string") {
        setImagePreview(reader.result);
      }
    });
    reader.addEventListener("error", () => {
      if (active) {
        setImagePreview("");
        setError(new ApiError("无法读取所选图片，请重新选择。", {
          code: "CARD_ASSET_READ_FAILED",
        }));
      }
    });
    reader.readAsDataURL(imageFile);

    return () => {
      active = false;
      if (reader.readyState === FileReader.LOADING) {
        reader.abort();
      }
    };
  }, [imageFile]);

  const update = (field: keyof ManagedCardInput, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };
  const updatePolicy = (
    field: keyof ManagedCardInput["policyVersions"],
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      policyVersions: { ...current.policyVersions, [field]: value },
    }));
  };

  const questions = questionsText
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const identityTitles = form.identityTitles.map((value) => value.trim()).filter(Boolean);
  const questionsValid =
    questions.length <= 6 && questions.every((value) => value.length <= 200);
  const titlesValid =
    identityTitles.length <= 8 && identityTitles.every((value) => value.length <= 80);
  const ownerValid = form.cardKind === "enterprise" || Boolean(form.ownerUserId?.trim());
  const valid =
    ownerValid &&
    (form.cardKind === "employee" || (Boolean(form.displayName.trim()) && Boolean(form.title.trim()))) &&
    questionsValid &&
    titlesValid;
  const selectedEmployee = employees.find((member) => member.userId === form.ownerUserId);
  const occupiedEmployeeIds = new Set(templateSources
    .filter((card) => card.cardKind === "employee" && card.id !== item?.id)
    .map((card) => card.ownerUserId)
    .filter((id): id is string => Boolean(id)));
  const configurationChoice = form.composerMode === "customize"
    ? "customize"
    : form.templateSourceCardId
      ? `copy:${form.templateSourceCardId}`
      : "default";

  const selectEmployee = (userId: string) => {
    const employee = employees.find((member) => member.userId === userId);
    setImageFile(undefined);
    setAvatarChanged(false);
    setForm((current) => ({
      ...current,
      ownerUserId: userId,
      displayName: employee?.displayName || current.displayName || "员工名片",
      title: employee?.jobTitle || "员工名片",
      avatarUrl: employee?.avatarUrl || "",
    }));
  };

  const setContactVisibility = (field: "mobile" | "email", checked: boolean) => {
    setForm((current) => ({
      ...current,
      employeeContactVisibility: checked
        ? [...new Set([...current.employeeContactVisibility, field])]
        : current.employeeContactVisibility.filter((value) => value !== field),
    }));
  };

  const addContactField = (kind: IdentityContactKind = "phone") => {
    setForm((current) => ({
      ...current,
      contactFields: [...current.contactFields, nextContactField(kind)].slice(0, 8),
    }));
  };

  const updateContactField = (id: string, patch: Partial<IdentityContactField>) => {
    setForm((current) => ({
      ...current,
      contactFields: current.contactFields.map((field) => (
        field.id === id ? { ...field, ...patch } : field
      )),
    }));
  };

  const removeContactField = (id: string) => {
    setForm((current) => ({
      ...current,
      contactFields: current.contactFields.filter((field) => field.id !== id),
    }));
  };

  const selectConfiguration = (value: string) => {
    if (value === "customize") {
      setForm((current) => ({
        ...current,
        composerMode: "customize",
        templateSourceCardId: "",
      }));
      return;
    }
    setForm((current) => ({
      ...current,
      composerMode: "default",
      templateSourceCardId: value.startsWith("copy:") ? value.slice(5) : "",
    }));
  };

  const chooseImage = (file?: File) => {
    if (!file) return;
    setError(undefined);
    if (!CARD_IMAGE_TYPES.has(file.type)) {
      setError(
        new ApiError("仅支持 PNG、JPEG 或 WebP 图片。", {
          code: "CARD_ASSET_UNSUPPORTED_TYPE",
        }),
      );
      return;
    }
    if (file.size > MAX_CARD_IMAGE_BYTES) {
      setError(
        new ApiError("图片不能超过 5 MiB。", {
          code: "CARD_ASSET_TOO_LARGE",
        }),
      );
      return;
    }
    setImageFile(file);
    setAvatarChanged(true);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    if (!item && form.composerMode === "customize") {
      onCustomize({
        input: {
          ...form,
          avatarUrl: form.cardKind === "employee" ? "" : form.avatarUrl,
          suggestedQuestions: questions,
          identityTitles,
          templateSourceCardId: "",
        },
        imageFile,
        avatarChanged,
        employeeMembershipId: selectedEmployee?.membershipId,
        employeeUserId: selectedEmployee?.userId,
        canonicalAvatarUrl: form.avatarUrl,
        identityPreview: {
          displayName: form.displayName,
          title: form.title,
          avatarUrl: imagePreview || resolveApiResourceUrl(form.avatarUrl),
          identityTitles,
          contactFields: form.contactFields,
        },
      });
      return;
    }
    setSaving(true);
    try {
      const uploaded = imageFile
        ? await adminApi.uploadCardAsset(imageFile)
        : undefined;
      const avatarUrl = uploaded?.url ?? form.avatarUrl;
      if (form.cardKind === "employee" && avatarChanged && selectedEmployee) {
        if (auth.user?.role !== "company_admin" && selectedEmployee.userId !== auth.user?.id) {
          throw new ApiError("只能修改自己的员工头像。", {
            code: "EMPLOYEE_AVATAR_PERMISSION_DENIED",
          });
        }
        const updatedEmployee = auth.user?.role === "company_admin"
          ? await memberApi.updateMember(selectedEmployee.membershipId, { avatarUrl })
          : await memberApi.updateMyProfile({ avatarUrl });
        setEmployees((current) => current.map((employee) => (
          employee.membershipId === updatedEmployee.membershipId ? updatedEmployee : employee
        )));
      }
      const input = {
        ...form,
        // Employee avatars belong to the enterprise employee profile. The card
        // request intentionally clears its legacy duplicate field.
        avatarUrl: form.cardKind === "employee" ? "" : avatarUrl,
        suggestedQuestions: questions,
        identityTitles,
      };
      if (item) {
        await adminApi.updateManagedCard(item.id, item.version, input);
        onSaved();
      } else {
        const created = await adminApi.createManagedCard(input);
        onSaved(created);
      }
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OverlayDrawer
      position="end"
      size="medium"
      open={open}
      onOpenChange={(_, data) => {
        if (!data.open && !saving) onClose();
      }}
    >
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              icon={<Dismiss24Regular />}
              aria-label="关闭名片编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {item
            ? `编辑${item.cardKind === "enterprise" ? "企业" : "员工"}名片`
            : `新建${createKind === "enterprise" ? "企业" : "员工"}名片`}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <form className="catalog-editor-form" onSubmit={submit} noValidate>
          <FormFeedback error={error} />

          {item && (
            <div className="immutable-resource-note">
              <strong>公开标识</strong>
              <code>{item.slug}</code>
              <span>安全链接由服务端生成，编辑时不会更改。</span>
            </div>
          )}

          {form.cardKind === "employee" ? (
            <>
              <section className="immutable-resource-note" aria-labelledby="employee-card-identity-title">
                <strong id="employee-card-identity-title">绑定企业员工</strong>
                <span>姓名、职位、头像和业务摘要统一来自企业员工；在这里上传头像也会同步到对应员工资料。</span>
              </section>
              <Field
                label="选择企业员工"
                required
                hint={item
                  ? "员工身份已绑定；姓名、职位和头像请在企业员工资料中维护。"
                  : "已有员工名片的员工不会重复创建；需要调整基础身份时请前往企业员工。"}
                validationState={attempted && !ownerValid ? "error" : "none"}
                validationMessage={attempted && !ownerValid ? "请选择一位有效企业员工。" : undefined}
              >
                <Select
                  aria-label="选择企业员工"
                  value={form.ownerUserId ?? ""}
                  disabled={saving || Boolean(item)}
                  onChange={(_, data) => selectEmployee(data.value)}
                >
                  <option value="">请选择企业员工</option>
                  {employees.map((member) => {
                    const occupied = !item && occupiedEmployeeIds.has(member.userId);
                    return (
                      <option
                        key={member.membershipId}
                        value={member.userId}
                        disabled={member.status !== "active" || occupied}
                      >
                        {member.displayName}{member.jobTitle ? ` · ${member.jobTitle}` : ""}
                        {member.status !== "active" ? "（已停用）" : occupied ? "（已有名片）" : ""}
                      </option>
                    );
                  })}
                </Select>
              </Field>
              <div className="immutable-resource-note">
                <strong>{selectedEmployee?.displayName || form.displayName || "尚未选择员工"}</strong>
                <span>{selectedEmployee?.jobTitle || form.title || "职位将在企业员工资料中维护"}</span>
                {(selectedEmployee?.businessSummary) && <span>{selectedEmployee.businessSummary}</span>}
              </div>
              <section className="card-composer-start" aria-labelledby="employee-contact-visibility-title">
                <div>
                  <strong id="employee-contact-visibility-title">公开联系方式</strong>
                  <span>联系方式来自企业员工资料；只公开你明确勾选的项目。</span>
                </div>
                <Checkbox
                  label="公开工作手机"
                  checked={form.employeeContactVisibility.includes("mobile")}
                  disabled={saving}
                  onChange={(_, data) => setContactVisibility("mobile", data.checked === true)}
                />
                <Checkbox
                  label="公开工作邮箱"
                  checked={form.employeeContactVisibility.includes("email")}
                  disabled={saving}
                  onChange={(_, data) => setContactVisibility("email", data.checked === true)}
                />
              </section>
            </>
          ) : (
            <>
              <div className="form-grid two-columns">
                <Field
                  label="企业名称"
                  required
                  validationState={attempted && !form.displayName.trim() ? "error" : "none"}
                  validationMessage={attempted && !form.displayName.trim() ? "请输入企业名称。" : undefined}
                >
                  <Input value={form.displayName} onChange={(_, data) => update("displayName", data.value)} disabled={saving} />
                </Field>
                <Field
                  label="业务定位或品牌标语"
                  required
                  validationState={attempted && !form.title.trim() ? "error" : "none"}
                  validationMessage={attempted && !form.title.trim() ? "请输入业务定位或品牌标语。" : undefined}
                >
                  <Input value={form.title} onChange={(_, data) => update("title", data.value)} disabled={saving} />
                </Field>
              </div>
            <div className="immutable-resource-note">
              <strong>企业官方名片</strong>
              <span>归企业所有，不绑定任何员工；发布后作为企业公开主页。</span>
            </div>
            </>
          )}

          <section className="card-identity-fields" aria-labelledby="card-identity-fields-title">
            <div className="form-section-heading compact">
              <div>
                <h2 id="card-identity-fields-title">基础名片信息</h2>
                <p>这些内容会真实保存，并显示在基础名片及可点击的联系快捷入口中。</p>
              </div>
            </div>
            <Field label="身份头衔" hint="每次添加一个身份，每项独立成行；最多 8 个。" validationState={attempted && !titlesValid ? "error" : "none"} validationMessage={attempted && !titlesValid ? "最多 8 个头衔，每个不超过 80 个字符。" : undefined}>
              <IdentityTitlesEditor values={form.identityTitles} disabled={saving} onChange={(values) => setForm((current) => ({ ...current, identityTitles: values }))} />
            </Field>

            <div className="card-contact-editor-heading">
              <div>
                <strong>联系与地址</strong>
                <span>企业和员工名片都可配置；公开页会恢复为可点击的小方形入口。</span>
              </div>
              <Button
                type="button"
                appearance="secondary"
                disabled={saving || form.contactFields.length >= 8}
                onClick={() => addContactField()}
              >
                添加联系方式
              </Button>
            </div>
            {form.contactFields.length ? (
              <div className="card-contact-editor-list">
                {form.contactFields.map((contact) => (
                  <div className="card-contact-editor-row" key={contact.id}>
                    <Field label="类型">
                      <Select
                        value={contact.kind}
                        disabled={saving}
                        onChange={(_, data) => {
                          const kind = data.value as IdentityContactKind;
                          updateContactField(contact.id, { kind, label: contactKindLabels[kind] });
                        }}
                      >
                        {Object.entries(contactKindLabels).map(([value, label]) => (
                          <option value={value} key={value}>{label}</option>
                        ))}
                      </Select>
                    </Field>
                    <Field label="显示名称">
                      <Input
                        value={contact.label}
                        disabled={saving}
                        onChange={(_, data) => updateContactField(contact.id, { label: data.value })}
                      />
                    </Field>
                    <Field label="内容">
                      <Input
                        value={contact.value}
                        disabled={saving}
                        placeholder={contact.kind === "location" ? "公司地址" : "公开显示的内容"}
                        onChange={(_, data) => updateContactField(contact.id, { value: data.value })}
                      />
                    </Field>
                    <Field label="点击目标（可选）" hint="支持 HTTPS、tel: 或 mailto:">
                      <Input
                        value={contact.href ?? ""}
                        disabled={saving}
                        placeholder={contact.kind === "website" ? "https://" : "留空则按内容自动处理"}
                        onChange={(_, data) => updateContactField(contact.id, { href: data.value })}
                      />
                    </Field>
                    <Button
                      type="button"
                      appearance="subtle"
                      icon={<Delete24Regular />}
                      aria-label={`删除${contact.label || "联系方式"}`}
                      disabled={saving}
                      onClick={() => removeContactField(contact.id)}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className="card-contact-editor-empty">
                尚未添加自定义联系方式。员工手机号与邮箱仍由“企业员工”资料控制；可在这里补充微信、企业地址、官网等。
              </div>
            )}
          </section>

          <section
            className={`card-image-upload ${form.cardKind}`}
            aria-label={form.cardKind === "enterprise" ? "企业 Logo" : "员工头像"}
          >
            <div className="card-image-preview">
              {imagePreview || form.avatarUrl ? (
                <img
                  src={imagePreview || resolveApiResourceUrl(form.avatarUrl)}
                  alt={form.cardKind === "enterprise" ? "企业 Logo 预览" : "员工头像预览"}
                />
              ) : (
                <span aria-hidden="true">
                  {(form.displayName.trim() || (form.cardKind === "enterprise" ? "企" : "员"))
                    .slice(0, 1)
                    .toUpperCase()}
                </span>
              )}
            </div>
            <div className="card-image-upload-copy">
              <strong>{form.cardKind === "enterprise" ? "企业 Logo" : "员工头像"}</strong>
              <span>
                {form.cardKind === "employee"
                  ? selectedEmployee
                    ? "支持 PNG、JPEG、WebP，最大 5 MiB；保存后同步到企业员工及其公开名片。"
                    : "请先选择企业员工，再为其上传头像。"
                  : "支持 PNG、JPEG、WebP，最大 5 MiB；保存时自动上传并压缩。"}
              </span>
              {imageFile && <em>{imageFile.name}</em>}
              <div className="card-image-upload-actions">
                <input
                  ref={imageInputRef}
                  className="visually-hidden"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={form.cardKind === "enterprise" ? "选择企业 Logo" : "选择员工头像"}
                  disabled={saving || (form.cardKind === "employee" && !selectedEmployee)}
                  onChange={(event) => {
                    chooseImage(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <Button
                  type="button"
                  appearance="secondary"
                  icon={<ArrowUpload24Regular />}
                  onClick={() => imageInputRef.current?.click()}
                  disabled={saving || (form.cardKind === "employee" && !selectedEmployee)}
                >
                  选择图片
                </Button>
                {(imageFile || form.avatarUrl) && (
                  <Button
                    type="button"
                    appearance="subtle"
                    icon={<Delete24Regular />}
                    onClick={() => {
                      setImageFile(undefined);
                      setAvatarChanged(true);
                      update("avatarUrl", "");
                    }}
                    disabled={saving || (form.cardKind === "employee" && !selectedEmployee)}
                  >
                    移除
                  </Button>
                )}
              </div>
            </div>
          </section>

          {!item && (
            <section className="card-composer-start" aria-labelledby="card-composer-start-title">
              <div>
                <strong id="card-composer-start-title">选择页面配置</strong>
                <span>默认配置和复制配置可以快速创建；自定义会先设计完整页面，确认后才创建名片。</span>
              </div>
              <Field
                label="配置来源"
                hint="这里只复制页面结构与展示规则；企业资料和员工身份始终读取后台最新数据。"
              >
                <Select
                  aria-label="配置来源"
                  value={configurationChoice}
                  disabled={saving}
                  onChange={(_, data) => selectConfiguration(data.value)}
                >
                  <option value="default">
                    使用{createKind === "enterprise" ? "企业" : "员工"}默认配置（快速创建）
                  </option>
                  {templateSources.map((source) => (
                    <option key={source.id} value={`copy:${source.id}`}>
                      复制「{source.displayName || source.slug}」的页面配置（快速创建）
                    </option>
                  ))}
                  <option value="customize">创建前自定义页面（从默认配置开始）</option>
                </Select>
              </Field>
            </section>
          )}

          <div className="form-grid two-columns">
            {form.cardKind === "enterprise" && <Field label="图片地址（可选）" hint="也可填写站内路径或公开 HTTPS 地址。">
              <Input
                value={form.avatarUrl}
                onChange={(_, data) => {
                  setImageFile(undefined);
                  update("avatarUrl", data.value);
                }}
                disabled={saving}
              />
            </Field>}
            <Field label="助手名称">
              <Input
                value={form.assistantName}
                onChange={(_, data) => update("assistantName", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <Field label="欢迎语">
            <Textarea
              value={form.welcomeMessage}
              onChange={(_, data) => update("welcomeMessage", data.value)}
              rows={4}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <Field
            label="建议问题"
            hint="每行一个问题，最多 6 条，每条不超过 200 个字符。"
            validationState={attempted && !questionsValid ? "error" : "none"}
            validationMessage={
              attempted && !questionsValid ? "请检查建议问题的数量和长度。" : undefined
            }
          >
            <Textarea
              value={questionsText}
              onChange={(_, data) => setQuestionsText(data.value)}
              rows={7}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <div className="form-section-heading secondary">
            <div>
              <h2>政策版本</h2>
              <p>公开前请确认政策版本与服务端发布内容一致。</p>
            </div>
          </div>
          <div className="form-grid two-columns">
            <Field label="隐私政策版本">
              <Input
                value={form.policyVersions.privacy}
                onChange={(_, data) => updatePolicy("privacy", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="对话提示版本">
              <Input
                value={form.policyVersions.chatNotice}
                onChange={(_, data) => updatePolicy("chatNotice", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="留资同意版本">
              <Input
                value={form.policyVersions.leadConsent}
                onChange={(_, data) => updatePolicy("leadConsent", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <div className="drawer-form-actions">
            <Button type="button" appearance="secondary" onClick={onClose} disabled={saving}>
              取消
            </Button>
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={saving}
            >
              {saving
                ? "正在保存"
                : !item && form.composerMode === "customize"
                  ? "下一步：设计名片页面"
                  : item
                    ? "保存名片"
                    : "创建名片"}
            </Button>
          </div>
        </form>
      </DrawerBody>
    </OverlayDrawer>
  );
}
