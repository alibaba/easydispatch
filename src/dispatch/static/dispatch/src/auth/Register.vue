<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-card class="mx-auto" max-width="500" style="margin-top: -140px;">
      <!-- <v-card class="mx-auto ma-4" max-width="600" flat outlined style="margin-top: -64px;"> -->
      <v-card-title>Register a New User</v-card-title>
      <v-card-text>
        <v-form>
          <v-container>
            <v-row>
              <v-col cols="12" md="12">
                <ValidationProvider name="Email" rules="required|email" immediate>
                  <v-text-field
                    v-model="email"
                    label="Email (It can NOT be modified later on...)"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    required
                  ></v-text-field>
                </ValidationProvider>
              </v-col>
              <v-col cols="12" md="12">
                <ValidationProvider name="Password" rules="required" immediate>
                  <v-text-field
                    v-model="password"
                    :type="'password'"
                    label="Password"
                    slot-scope="{ errors, valid }"
                    :success="valid"
                    :error-messages="errors"
                    required
                  ></v-text-field>
                </ValidationProvider>
              </v-col>
              <v-col cols="12" md="12">
                <ValidationProvider name="confirm" rules="required|password:@Password" immediate>
                  <v-text-field
                    v-model="re_password"
                    :type="'password'"
                    label="confirm password"
                    slot-scope="{ errors, valid }"
                    :success="valid"
                    :error-messages="errors"
                    required
                  ></v-text-field>
                </ValidationProvider>
              </v-col>
              <v-col cols="12" md="12">
                <v-tabs height="30px">
                  <v-tab>create organization</v-tab>
                  <v-tab>join organization</v-tab>

                  <v-tab-item>
                    <v-card flat>
                      <v-text-field
                        v-model="org_code"
                        label="please enter organization code."
                        required
                      ></v-text-field>
                    </v-card>
                  </v-tab-item>
                  <v-tab-item>
                    <v-card flat>
                      <v-text-field
                        v-model="en_code"
                        label="please enter organization invitation code"
                        required
                      ></v-text-field>
                    </v-card>
                  </v-tab-item>
                </v-tabs>
              </v-col>
              <!-- <v-col cols="8" md="8">
                <v-text-field v-model="en_code" label="organization" required></v-text-field>
              </v-col>
              <v-col cols="4" md="4">
                <v-btn fab dark small color="indigo" @click="showCreateEditDialog(true)">
                  <v-icon dark>mdi-plus</v-icon>
                </v-btn>
              </v-col>-->
            </v-row>
          </v-container>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-list-item three-line>
          <v-list-item-content>
            <v-list-item-subtitle>
              Already have an account?
              <router-link :to="{ path: '/login' }">Login</router-link>
            </v-list-item-subtitle>
          </v-list-item-content>
          <v-row align="center" justify="end" style="width:50px">
            <v-btn color="info" @click="check_password()" :disabled="invalid || !validated">
              Register
              <template v-slot:loader>
                <v-progress-linear indeterminate color="white" />
              </template>
            </v-btn>
          </v-row>
        </v-list-item>
      </v-card-actions>
      <CreateEditDialog />
    </v-card>
  </ValidationObserver>
</template>

<script>
import { mapActions } from "vuex";

import { mapFields } from "vuex-map-fields";
import CreateEditDialog from "./CreateEditDialog.vue";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required, email } from "vee-validate/dist/rules";
extend("email", email);

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
  components: {
    CreateEditDialog,
    ValidationProvider,
    ValidationObserver,
  },
  data() {
    return {
      email: "",
      password: "",
      re_password: "",
      org_code: "",
      en_code: "",
    };
  },
  methods: {
    ...mapActions("auth", [
      "register",
      "showCreateEditDialog",
      "setRegisterCode",
    ]),
    isSucceedPassword(s) {
      var regu = "^[0-9a-zA-Z]{8,16}$";
      var re = new RegExp(regu);
      if (re.test(s)) {
        return true;
      } else {
        return false;
      }
    },
    check_password() {
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
      if (!this.en_code && !this.org_code) {
        this.$store.commit(
          "app/SET_SNACKBAR",
          {
            text: "organization code or organization invitation code is necessary.",
            color: "red",
          },
          { root: true }
        );
        return false;
      }
      this.register({
        email: this.email,
        password: this.password,
        en_code: this.en_code,
        org_code: this.org_code,
      });
    },
  },
  watch: {
    org_code: function (newData) {
      if (newData) {
        this.en_code = "";
      }
    },
    en_code: function (newData) {
      if (newData) {
        this.org_code = "";
      }
    },
  },
  computed: {
    // ...mapFields("auth", ["org.en_code"]),
  },
};
</script>

<style scoped></style>
