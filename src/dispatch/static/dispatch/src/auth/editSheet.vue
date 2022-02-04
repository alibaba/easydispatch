<template>
  <v-navigation-drawer v-model="showEdit" app clipped right width="500">
    <template v-slot:prepend>
      <v-list-item two-line>
        <v-list-item-content>
          <v-list-item-title class="title">Edit</v-list-item-title>
          <v-list-item-subtitle>User</v-list-item-subtitle>
        </v-list-item-content>
        <v-btn icon color="primary" :loading="loading" @click="check_password()">
          <v-icon>save</v-icon>
        </v-btn>
        <v-btn icon color="secondary" @click="closeEdit">
          <v-icon>close</v-icon>
        </v-btn>
      </v-list-item>
    </template>
    <v-card flat>
      <v-card-text>
        <v-container grid-list-md>
          <v-layout wrap>
            <v-flex xs12>
              <span class="subtitle-2">Details</span>
            </v-flex>
            <v-flex xs12>
              <v-text-field v-model="email" disabled label="Email" hint="User's email." />
            </v-flex>
            <v-flex xs12>
              <v-select
                v-model="role"
                label="Role"
                :items="roles"
                hint="The user's current role."
                :disabled="!userInfo || userInfo.role!='Owner' "
              />
            </v-flex>
            <v-flex xs12>
              <v-switch
                v-model="is_active"
                hint="Whether the account is activated or not."
                label="Activated"
              />
            </v-flex>
            <v-flex xs12>
              <team-select v-model="team" rules="required"></team-select>
            </v-flex>
            <v-flex xs12>
              <team-combobox
                v-model="managed_teams"
                label="Managed Teams"
                hint="Managed Teams if this is an owner or planner"
                v-show="role!='Worker'"
              />
            </v-flex>
            <v-flex xs12 v-if="password_visible">
              <span class="subtitle-2">Change Password:</span>
            </v-flex>
            <v-col cols="12" md="12" v-if="password_visible">
              <ValidationProvider name="Old Password" rules immediate>
                <v-text-field
                  autocomplete="new-password"
                  v-model="old_password"
                  :type="'password'"
                  label="Old Password"
                  slot-scope="{ errors, valid }"
                  :success="valid"
                  :error-messages="errors"
                  required
                ></v-text-field>
              </ValidationProvider>
            </v-col>
            <v-col cols="12" md="12" v-if="password_visible">
              <ValidationProvider name="Password" rules immediate>
                <v-text-field
                  autocomplete="new-password"
                  v-model="password"
                  :type="'password'"
                  label="New Password"
                  slot-scope="{ errors, valid }"
                  :success="valid"
                  :error-messages="errors"
                  required
                ></v-text-field>
              </ValidationProvider>
            </v-col>
            <v-col cols="12" md="12" v-if="password_visible">
              <ValidationProvider name="confirm" rules="password:@Password" immediate>
                <v-text-field
                  autocomplete="new-password"
                  v-model="re_password"
                  :type="'password'"
                  label="Confirm New Password"
                  slot-scope="{ errors, valid }"
                  :success="valid"
                  :error-messages="errors"
                  required
                ></v-text-field>
              </ValidationProvider>
            </v-col>
          </v-layout>
        </v-container>
      </v-card-text>
    </v-card>
  </v-navigation-drawer>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import TeamSelect from "@/team/TeamSelect.vue";
import TeamCombobox from "@/team/TeamCombobox.vue";
import TeamApi from "@/team/api.js";
import { ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import { mapState } from "vuex";

extend("required", {
  ...required,
  message: "This field is required",
});

extend("password", {
  params: ["target"],
  validate(value, { target }) {
    return value === target;
  },
  message: "Password confirmation does not match",
});

export default {
  name: "UserEditSheet",

  components: {
    TeamSelect,
    TeamCombobox,
    ValidationProvider,
  },
  data() {
    return {
      roles: ["Worker", "Planner", "Owner", "Customer"],
      team: null,
      password: null,
      re_password: null,
      old_password: null,
    };
  },

  computed: {
    ...mapFields("auth", [
      "selected.email",
      "selected.role",
      "selected.id",
      "selected.loading",
      "selected.default_team_id",
      "selected.managed_teams",
      "selected.is_active",
      "dialogs.showEdit",
    ]),
    ...mapState("auth", ["userInfo"]),
    password_visible() {
      return this.userInfo.email == this.email;
    },
  },

  methods: {
    ...mapActions("auth", ["save", "closeEdit"]),
    getTeamById(id) {
      TeamApi.get(id)
        .then((response) => {
          if (response.data) {
            this.team = response.data;
          }
        })
        .catch((err) => {
          this.team = null;
        });
    },
    isSucceedPassword(s) {
      var regu = "(?=.*[0-9])(?=.*[a-zA-Z]).{8,16}";
      var re = new RegExp(regu);
      if (re.test(s)) {
        return true;
      } else {
        return false;
      }
    },
    check_password() {
      if (this.password) {
        if (!this.password || !this.re_password) {
          this.$store.commit(
            "app/SET_SNACKBAR",
            {
              text: "Please enter the  password.",
              color: "red",
            },
            { root: true }
          );
          return false;
        }
        if (!this.isSucceedPassword(this.password)) {
          this.$store.commit(
            "app/SET_SNACKBAR",
            {
              text: "Please enter a password of 8-16 digits plus letters.",
              color: "red",
            },
            { root: true }
          );
          return false;
        }
        if (this.password != this.re_password) {
          this.$store.commit(
            "app/SET_SNACKBAR",
            {
              text: "The two passwords are inconsistent.",
              color: "red",
            },
            { root: true }
          );
          return false;
        }
      }
      this.save({
        password: this.password,
        old_password: this.old_password,
        is_me: this.userInfo.email == this.email,
      });
    },
  },
  watch: {
    id: function (value, oldValue) {
      this.getTeamById(this.default_team_id);
    },
    team: function (value, oldValue) {
      if (value) {
        this.default_team_id = value.id;
      }
    },
    default_team_id: function (value, oldValue) {
      if (value && value != -1) {
        this.getTeamById(value);
      }
    },
  },
};
</script>
