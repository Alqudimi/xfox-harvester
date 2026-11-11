/** User management (admin). */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Shield, UserPlus } from "lucide-react";
import { api, type UserPublic } from "../../lib/api";
import { useI18n } from "../../i18n";
import { useAuth } from "../auth/authContext";
import { SectionHeader } from "../../components/ui/card";
import { Badge, Button, Field, Input, Select, Spinner } from "../../components/ui/primitives";
import { TD, THead, TRow, TableWrap } from "../../components/ui/table";
import { ConfirmDialog, Dialog } from "../../components/ui/dialog";
import { useToast } from "../../components/ui/toast";
import { formatDateTime } from "../../lib/format";

export function Users() {
  const { t } = useI18n();
  const { user: current, refresh } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserPublic[]>("/api/users"),
  });

  const [addOpen, setAddOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<UserPublic | null>(null);
  const [deleting, setDeleting] = useState<UserPublic | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
  };

  const changeRole = useMutation({
    mutationFn: ({ user, role }: { user: UserPublic; role: string }) =>
      api.patch(`/api/users/${user.id}`, { role }),
    onSuccess: () => {
      invalidate();
      if (current) void refresh();
    },
    onError: (error) =>
      toast.error(
        error instanceof Error && error.message.includes("cannot_demote_self")
          ? t("usr.cannotDemoteSelf")
          : t("common.unknownError"),
      ),
  });

  const toggleActive = useMutation({
    mutationFn: (user: UserPublic) =>
      api.patch(`/api/users/${user.id}`, { is_active: !user.is_active }),
    onSuccess: invalidate,
    onError: () => toast.error(t("common.unknownError")),
  });

  const remove = useMutation({
    mutationFn: (user: UserPublic) => api.delete(`/api/users/${user.id}`),
    onSuccess: () => {
      setDeleting(null);
      invalidate();
      toast.success(t("common.success"));
    },
    onError: (error) =>
      toast.error(
        error instanceof Error && error.message.includes("cannot_delete_self")
          ? t("usr.cannotDeleteSelf")
          : t("common.unknownError"),
      ),
  });

  const rows = users.data ?? [];

  return (
    <div>
      <SectionHeader
        title={t("usr.title")}
        subtitle={t("usr.subtitle")}
        action={
          <Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
            {t("usr.add")}
          </Button>
        }
      />

      {users.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <TableWrap>
          <THead
            columns={[
              t("auth.username"),
              t("usr.role"),
              t("common.status"),
              t("usr.lastLogin"),
              t("usr.createdAt"),
              t("common.actions"),
            ]}
          />
          <tbody>
            {rows.map((user) => (
              <TRow key={user.id}>
                <TD>
                  <p className="font-bold text-ink-100">{user.username}</p>
                  {user.display_name && <p className="text-[11px] text-ink-400">{user.display_name}</p>}
                </TD>
                <TD>
                  <Select
                    className="h-8 w-32 text-xs"
                    value={user.role}
                    disabled={user.id === current?.id}
                    onChange={(event) => changeRole.mutate({ user, role: event.target.value })}
                  >
                    <option value="admin">{t("role.admin")}</option>
                    <option value="operator">{t("role.operator")}</option>
                    <option value="viewer">{t("role.viewer")}</option>
                  </Select>
                </TD>
                <TD>
                  <Badge tone={user.is_active ? "green" : "neutral"}>
                    {user.is_active ? t("usr.active") : t("common.disabled")}
                  </Badge>
                </TD>
                <TD className="text-xs text-ink-400">{formatDateTime(user.last_login_at)}</TD>
                <TD className="text-xs text-ink-400">{formatDateTime(user.created_at)}</TD>
                <TD>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      title={t("usr.changePassword")}
                      onClick={() => setPasswordUser(user)}
                    >
                      <KeyRound className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title={user.is_active ? t("common.disabled") : t("usr.active")}
                      disabled={user.id === current?.id}
                      onClick={() => toggleActive.mutate(user)}
                    >
                      <Shield className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-400 hover:bg-red-500/10"
                      disabled={user.id === current?.id}
                      onClick={() => setDeleting(user)}
                    >
                      ✕
                    </Button>
                  </div>
                </TD>
              </TRow>
            ))}
          </tbody>
        </TableWrap>
      )}

      <AddUserDialog open={addOpen} onClose={() => setAddOpen(false)} onDone={invalidate} />

      <ChangePasswordDialog user={passwordUser} onClose={() => setPasswordUser(null)} />

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title={t("common.delete")}
        message={t("usr.deleteConfirm")}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
      />
    </div>
  );
}

function AddUserDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/users", {
        username,
        password,
        display_name: displayName || null,
        role,
      }),
    onSuccess: () => {
      onClose();
      setUsername("");
      setDisplayName("");
      setPassword("");
      setRole("viewer");
      onDone();
      toast.success(t("usr.userCreated"));
    },
    onError: (error) =>
      toast.error(
        error instanceof Error && error.message.includes("username_taken")
          ? t("common.error")
          : t("common.unknownError"),
      ),
  });

  return (
    <Dialog open={open} onClose={onClose} title={t("usr.add")}>
      <div className="space-y-4">
        <Field label={t("auth.username")}>
          <Input value={username} onChange={(event) => setUsername(event.target.value)} />
        </Field>
        <Field label={`${t("auth.displayName")} (${t("common.optional")})`}>
          <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </Field>
        <Field label={t("auth.password")}>
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <Field label={t("usr.role")}>
          <Select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="admin">{t("role.admin")} — {t("role.adminDesc")}</option>
            <option value="operator">{t("role.operator")} — {t("role.operatorDesc")}</option>
            <option value="viewer">{t("role.viewer")} — {t("role.viewerDesc")}</option>
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            loading={create.isPending}
            disabled={username.length < 3 || password.length < 8}
            onClick={() => create.mutate()}
          >
            {t("common.add")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function ChangePasswordDialog({
  user,
  onClose,
}: {
  user: UserPublic | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const [password, setPassword] = useState("");

  const change = useMutation({
    mutationFn: () => api.patch(`/api/users/${user!.id}`, { password }),
    onSuccess: () => {
      onClose();
      setPassword("");
      toast.success(t("auth.passwordChanged"));
    },
    onError: () => toast.error(t("common.unknownError")),
  });

  return (
    <Dialog open={user !== null} onClose={onClose} title={t("usr.changePassword")}>
      <div className="space-y-4">
        <p className="text-xs text-ink-400">{user?.username}</p>
        <Field label={t("auth.newPassword")}>
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button size="sm" loading={change.isPending} disabled={password.length < 8} onClick={() => change.mutate()}>
            {t("common.save")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
